from datetime import datetime
import io
import json
import os
import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF
import pandas as pd
import requests
import streamlit as st

DATA_FILE = "multi_factory_data.json"

# --- 0. دالة تحويل الأرقام إلى نصوص عربية (تفقيط لسند القبض) ---
def number_to_arabic_words(num):
    if num == 0:
        return "صفر"
    
    ones = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
    teens = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
    tens = ["", "عشرة", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
    hundreds = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"]
    
    def convert_group(n):
        res = []
        h = n // 100
        rem = n % 100
        if h > 0:
            res.append(hundreds[h])
        if rem > 0:
            if rem < 10:
                res.append(ones[rem])
            elif rem < 20:
                res.append(teens[rem - 10])
            else:
                t = rem // 10
                u = rem % 10
                if u > 0:
                    res.append(ones[u] + " و " + tens[t])
                else:
                    res.append(tens[t])
        return " و ".join(res)
    
    parts = []
    
    b = num // 1000000000
    if b > 0:
        if b == 1: parts.append("مليار")
        elif b == 2: parts.append("ملياران")
        elif 3 <= b <= 10: parts.append(convert_group(b) + " مليارات")
        else: parts.append(convert_group(b) + " مليار")
    num %= 1000000000
    
    m = num // 1000000
    if m > 0:
        if m == 1: parts.append("مليون")
        elif m == 2: parts.append("مليونان")
        elif 3 <= m <= 10: parts.append(convert_group(m) + " ملايين")
        else: parts.append(convert_group(m) + " مليون")
    num %= 1000000
    
    k = num // 1000
    if k > 0:
        if k == 1: parts.append("ألف")
        elif k == 2: parts.append("ألفان")
        elif 3 <= k <= 10: parts.append(convert_group(k) + " آلاف")
        else: parts.append(convert_group(k) + " ألف")
    num %= 1000
    
    if num > 0:
        parts.append(convert_group(num))
        
    return " و ".join(parts).strip()


# --- 1. إدارة ملف البيانات والتخزين الدائم للنظام ---
def get_default_factory_data(factory_name, admin_user, admin_pass):
    return {
        "info": {"factory_name": factory_name},
        "users": {
            admin_user: {
                "password": admin_pass,
                "role": "admin",
                "name": f"مدير {factory_name}",
            }
        },
        "inventory": {
            "الحنفية": 0.0,
            "البانكة": 0.0,
            "الماطور": 0.0,
            "التوماتيك": 0.0,
            "الطواف": 0.0,
            "الراديتر": 0.0,
            "زواية القاعدة": 0.0,
            "المنيوم القاعدة 1.35m": 0.0,
            "الجكنة": 0.0,
            "واشر حديد": 0.0,
            "واشر بلاستك": 0.0,
            "زبانة": 0.0,
            "كبلري 1.7m": 0.0,
            "كويل": 0.0,
            "بوري ربع 1.5m": 0.0,
            "طبقة وربع بليت": 0.0,
        },
        "finished_goods": {
            "براد حنفية واحدة": 0,
            "براد حنفيتين": 0,
        },
        "agents": {},
        "bom": {
            "براد حنفية واحدة": {
                "الحنفية": 1,
                "البانكة": 1,
                "الماطور": 1,
                "التوماتيك": 1,
                "الطواف": 1,
                "الراديتر": 1,
                "زواية القاعدة": 4,
                "المنيوم القاعدة 1.35m": 1,
                "الجكنة": 1,
                "واشر حديد": 1,
                "واشر بلاستك": 1,
                "زبانة": 1,
                "كبلري 1.7m": 1,
                "كويل": 1,
                "بوري ربع 1.5m": 1,
                "طبقة وربع بليت": 1.25,
            },
            "براد حنفيتين": {
                "الحنفية": 2,
                "البانكة": 1,
                "الماطور": 1,
                "التوماتيك": 1,
                "الطواف": 1,
                "الراديتر": 1,
                "زواية القاعدة": 4,
                "المنيوم القاعدة 1.35m": 1,
                "الجكنة": 2,
                "واشر حديد": 2,
                "واشر بلاستك": 2,
                "زبانة": 2,
                "كبلري 1.7m": 1,
                "كويل": 1,
                "بوري ربع 1.5m": 1,
                "طبقة وربع بليت": 1.25,
            },
        },
        "receipt_counter": 1001,
        "sales_history": [],
        "production_history": [],
    }


def load_all_factories():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for f_name, f_data in data.items():
                    if "finished_goods" not in f_data:
                        f_data["finished_goods"] = {
                            model: 0 for model in f_data.get("bom", {}).keys()
                        }
                    if "agents" not in f_data:
                        f_data["agents"] = {}
                    if "sales_history" not in f_data:
                        f_data["sales_history"] = []
                    if "production_history" not in f_data:
                        f_data["production_history"] = []
                    for ag_name, ag_info in f_data["agents"].items():
                        if not isinstance(ag_info, dict):
                            f_data["agents"][ag_name] = {
                                "phone": "",
                                "debt_usd": 0.0,
                                "transactions": [],
                            }
                        else:
                            if "debt_usd" not in ag_info and "debt" in ag_info:
                                ag_info["debt_usd"] = ag_info["debt"]
                            if "debt_usd" not in ag_info:
                                ag_info["debt_usd"] = 0.0
                            if "transactions" not in ag_info:
                                ag_info["transactions"] = []
                            if "phone" not in ag_info:
                                ag_info["phone"] = ""
                return data
        except Exception:
            return {}
    else:
        return {}


def save_all_factories(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# --- 2. دوال الطباعة والـ PDF ---
def ar(text):
    if not text:
        return ""
    reshaped_text = arabic_reshaper.reshape(str(text))
    return get_display(reshaped_text)


@st.cache_resource
def ensure_arabic_font():
    font_path = "Amiri-Regular.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"
            response = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(response.content)
        except Exception as e:
            st.error(f"خطأ في تحميل الخط العربي: {e}")
    return font_path


def generate_receipt_pdf(
    factory_name,
    customer_name,
    date_str,
    items_data,
    grand_total_usd,
    paid_amount_usd,
    remaining_amount_usd,
    exchange_rate,
    receipt_no,
):
    font_path = ensure_arabic_font()
    pdf = FPDF()
    pdf.add_page()

    if os.path.exists(font_path):
        pdf.add_font("Amiri", "", font_path)
        pdf.set_font("Amiri", "", 20)
    else:
        pdf.set_font("Arial", "B", 16)

    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 10, ar(factory_name), ln=True, align="C")
    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 16)
    pdf.cell(0, 8, ar("قائمة حساب (بالدولار الأمريكي)"), ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 10)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(0, 6, ar(f"رقم القائمة: #{receipt_no}"), ln=True, align="R")
    pdf.cell(0, 6, ar(f"التاريخ: {date_str}"), ln=True, align="R")
    pdf.cell(0, 6, ar(f"اسم العميل / الوكيل: {customer_name}"), ln=True, align="R")
    pdf.cell(0, 6, ar(f"سعر صرف الدولار المعتمد: {exchange_rate:,.0f} د.ع"), ln=True, align="R")
    pdf.ln(4)

    if items_data:
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)

        col_widths = [35, 40, 20, 35, 60]
        headers = [
            ar("الإجمالي ($)"),
            ar("السعر ($)"),
            ar("الكمية"),
            ar("الإجمالي (د.ع)"),
            ar("نوع البراد"),
        ]
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 8, h, border=1, align="C", fill=True)
        pdf.ln()

        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(33, 37, 41)

        for item in items_data:
            item_total_iqd = item['total_usd'] * exchange_rate
            pdf.cell(col_widths[0], 8, f"${item['total_usd']:,.2f}", border=1, align="C")
            pdf.cell(col_widths[1], 8, f"${item['price_usd']:,.2f}", border=1, align="C")
            pdf.cell(col_widths[2], 8, str(item["count"]), border=1, align="C")
            pdf.cell(col_widths[3], 8, f"{item_total_iqd:,.0f}", border=1, align="C")
            pdf.cell(col_widths[4], 8, ar(item["model"]), border=1, align="C")
            pdf.ln()

    grand_total_iqd = grand_total_usd * exchange_rate
    paid_iqd = paid_amount_usd * exchange_rate
    remaining_iqd = remaining_amount_usd * exchange_rate

    pdf.set_fill_color(241, 245, 249)
    pdf.cell(50, 7, f"${grand_total_usd:,.2f}  /  {grand_total_iqd:,.0f} د.ع", border=1, align="C", fill=True)
    pdf.cell(140, 7, ar("المبلغ الإجمالي للفاتورة"), border=1, align="C", fill=True)
    pdf.ln()
    pdf.cell(50, 7, f"${paid_amount_usd:,.2f}  /  {paid_iqd:,.0f} د.ع", border=1, align="C")
    pdf.cell(140, 7, ar("المبلغ المدفوع نقدياً"), border=1, align="C")
    pdf.ln()
    pdf.cell(50, 7, f"${remaining_amount_usd:,.2f}  /  {remaining_iqd:,.0f} د.ع", border=1, align="C")
    pdf.cell(140, 7, ar("المبلغ المتبقي"), border=1, align="C")
    pdf.ln(15)

    pdf.cell(0, 6, ar("توقيع المستلم: .........................."), ln=True, align="L")
    return bytes(pdf.output())


def generate_payment_pdf(
    factory_name, agent_name, date_str, amount_usd, remaining_debt_usd, old_debt_usd, exchange_rate, receipt_no, note=""
):
    font_path = ensure_arabic_font()
    pdf = FPDF(orientation="P", unit="mm", format="A5")
    pdf.set_margins(8, 8, 8)
    pdf.add_page()

    if os.path.exists(font_path):
        pdf.add_font("Amiri", "", font_path)
        pdf.set_font("Amiri", "", 13)
    else:
        pdf.set_font("Arial", "B", 12)

    pdf.set_text_color(0, 0, 0)
    
    pdf.set_y(8)
    pdf.cell(0, 6, ar(factory_name), ln=True, align="C")
    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 11)
    pdf.cell(0, 6, ar("سند قبض"), ln=True, align="C")
    pdf.ln(2)

    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 9)
    pdf.set_line_width(0.3)
    
    pdf.cell(66, 6, ar(f"رقم المستند: {receipt_no}"), border=1, align="R")
    pdf.cell(66, 6, ar(f"التاريخ: {date_str}"), border=1, align="R", ln=True)
    pdf.cell(132, 6, ar(f"استلمت من السيد / {agent_name}"), border=1, align="R", ln=True)
    
    amount_iqd = int(round(amount_usd * exchange_rate))
    amount_in_words = f"مبلغ وقدره: {number_to_arabic_words(amount_iqd)} دينار عراقي فقط لا غير"
    
    # حفظ الإحداثيات لرسم خطوط الشطب فوق خانة التفقيط لمنع التزوير
    x_start_box = pdf.get_x()
    y_start_box = pdf.get_y()
    
    pdf.set_fill_color(240, 243, 246)
    pdf.cell(132, 6, ar(amount_in_words), border=1, align="R", fill=True, ln=True)
    
    # --- إضافة شخطات مائلة (تشطيب أمان) فوق خانة المبلغ بالحروف ---
    pdf.set_line_width(0.2)
    pdf.set_draw_color(150, 150, 150) # لون رمادي خفيف للشخطات المائلة
    
    # رسم خطوط مائلة متوازية داخل المستطيل الخاص بمبلغ التفقيط
    box_x = 8.5
    box_y = y_start_box
    box_w = 131
    box_h = 6
    step = 5  # المسافة بين الشخطات المائلة
    
    current_x = box_x + 4
    while current_x < box_x + box_w:
        pdf.line(current_x, box_y + box_h, current_x + 3, box_y)
        current_x += step
        
    pdf.set_draw_color(0, 0, 0) # إعادة اللون الأسود للإطار العادي
    pdf.set_line_width(0.3)
    # -------------------------------------------------------------
    
    paid_iqd_val = int(round(amount_usd * exchange_rate))
    pdf.cell(66, 6, ar(f"سعر الصرف: {exchange_rate:,.0f} د.ع"), border=1, align="R")
    pdf.cell(66, 6, ar(f"المبلغ المدفوع: ${amount_usd:,.2f}  /  {paid_iqd_val:,} د.ع"), border=1, align="R", fill=True, ln=True)
    
    note_text = f"الملاحظات: {note}" if note else "الملاحظات: -"
    pdf.cell(132, 6, ar(note_text), border=1, align="R", ln=True)
    
    rem_iqd = int(round(remaining_debt_usd * exchange_rate))
    old_iqd = int(round(old_debt_usd * exchange_rate))
    pdf.cell(132, 6, ar(f"الرصيد السابق: ${old_debt_usd:,.2f}  /  {old_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
    pdf.cell(132, 6, ar(f"الرصيد بعد التسديد: ${remaining_debt_usd:,.2f}  /  {rem_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
    
    pdf.ln(4)
    pdf.cell(132, 6, ar("توقيع وختم القابض: .........................."), ln=True, align="L")
    
    end_y = pdf.get_y() + 2
    pdf.set_line_width(0.5)
    pdf.rect(8, 8, 132, end_y - 8)
    
    return bytes(pdf.output())


# --- 3. إعداد الصفحة والجلسة ---
st.set_page_config(
    page_title="نظام إدارة المخزون والمعامل والوكلاء",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

all_factories = load_all_factories()

query_params = st.query_params
saved_factory = query_params.get("factory", None)
saved_user = query_params.get("user", None)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.factory_key = None
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.user_fullname = ""

if not st.session_state.authenticated and saved_factory and saved_user:
    if saved_factory in all_factories:
        factory_users = all_factories[saved_factory].get("users", {})
        if saved_user in factory_users:
            st.session_state.authenticated = True
            st.session_state.factory_key = saved_factory
            st.session_state.username = saved_user
            st.session_state.role = factory_users[saved_user]["role"]
            st.session_state.user_fullname = factory_users[saved_user]["name"]

# --- 4. شاشة تسجيل الدخول أو إنشاء حساب جديد ---
if not st.session_state.authenticated:
    st.title("❄️ نظام إدارة وتتبع المعامل والمخزون")

    login_tab, register_tab = st.tabs(
        ["🔑 تسجيل الدخول لمعمل", "🏭 إنشاء حساب معمل جديد"]
    )

    with login_tab:
        st.subheader("دخول إلى حساب المعمل")
        factory_list = list(all_factories.keys())
        if not factory_list:
            st.info("💡 لا توجد معامل مسجلة بالنظام حالياً. يرجى إنشاء حساب معمل جديد.")
        else:
            selected_factory = st.selectbox("اختر المعمل:", factory_list)
            username_input = st.text_input("اسم المستخدم:")
            password_input = st.text_input("كلمة المرور:", type="password")

            if st.button("تسجيل الدخول", type="primary", use_container_width=True):
                factory_users = all_factories[selected_factory].get("users", {})
                if (
                    username_input in factory_users
                    and factory_users[username_input]["password"] == password_input
                ):
                    st.session_state.authenticated = True
                    st.session_state.factory_key = selected_factory
                    st.session_state.username = username_input
                    st.session_state.role = factory_users[username_input]["role"]
                    st.session_state.user_fullname = factory_users[username_input]["name"]

                    st.query_params["factory"] = selected_factory
                    st.query_params["user"] = username_input

                    st.success("تم تسجيل الدخول بنجاح!")
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة!")

    with register_tab:
        st.subheader("تسجيل معمل جديد بالنظام")
        new_factory_name = st.text_input("اسم المعمل الجديد:")
        admin_user = st.text_input("اسم مستخدم المدير:")
        admin_pass = st.text_input("كلمة مرور المدير:", type="password")

        if st.button("🚀 إنشاء المعمل وبدء الاستخدام", type="primary", use_container_width=True):
            if not new_factory_name or not admin_user or not admin_pass:
                st.error("يرجى إدخال كافة البيانات المطلوبة.")
            elif new_factory_name in all_factories:
                st.error("اسم هذا المعمل مستخدم بالفعل!")
            else:
                all_factories[new_factory_name] = get_default_factory_data(
                    new_factory_name, admin_user, admin_pass
                )
                save_all_factories(all_factories)
                st.success(f"✅ تم إنشاء [{new_factory_name}] بنجاح!")

    st.stop()

# --- 5. تحميل بيانات المعمل الحالي ---
current_factory_name = st.session_state.factory_key
if current_factory_name not in all_factories:
    st.error("حدث خطأ في تحميل بيانات المعمل.")
    st.session_state.authenticated = False
    st.query_params.clear()
    st.rerun()

factory_data = all_factories[current_factory_name]
if "finished_goods" not in factory_data:
    factory_data["finished_goods"] = {model: 0 for model in factory_data.get("bom", {}).keys()}
if "agents" not in factory_data:
    factory_data["agents"] = {}

# --- 6. الواجهة الرئيسية وشريط المستخدم ---
st.title(f"❄️ {current_factory_name}")

col_u1, col_u2 = st.columns([3, 1])
with col_u1:
    role_badge = "👑 مدير المعمل" if st.session_state.role == "admin" else "👷 موظف"
    st.info(f"المستخدم الحالي: **{st.session_state.user_fullname}** | {role_badge}")
with col_u2:
    if st.button("🚪 تسجيل الخروج", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.factory_key = None
        st.query_params.clear()
        st.rerun()

st.write("---")

# --- 7. التبويبات بحسب الصلاحيات ---
if st.session_state.role == "admin":
    tabs = st.tabs([
        "📊 التقارير الشاملة",
        "🤝 إدارة الوكلاء والديون",
        "🛒 بيع براد / قائمة حساب",
        "🏭 تسجيل إنتاج براد",
        "📦 إدارة المخزون",
        "👥 إدارة الحسابات والموظفين",
        "📄 تصدير Excel",
        "➕ إضافة مادة جديدة",
        "🛠️ أنواع البرادات (BOM)",
        "⚠️ فورمات كامل",
    ])
else:
    tabs = st.tabs([
        "🛒 بيع براد / قائمة حساب",
        "🤝 الوكلاء والديون",
        "🏭 تسجيل إنتاج براد",
        "📦 المخزون الحالي",
    ])

# --- تبويب التقارير (للمدير فقط) ---
if st.session_state.role == "admin":
    with tabs[0]:
        st.header("📊 التقارير الشاملة والإحصائيات (بالدولار)")

        today_str = datetime.now().strftime("%Y-%m-%d")
        current_month_str = datetime.now().strftime("%Y-%m")

        sales_df = pd.DataFrame(factory_data.get("sales_history", []))

        today_sales_count, today_revenue_usd = 0, 0
        month_sales_count, month_revenue_usd = 0, 0

        if not sales_df.empty and "date" in sales_df.columns:
            sales_df["date"] = pd.to_datetime(sales_df["date"], errors="coerce")
            today_sales = sales_df[sales_df["date"].dt.strftime("%Y-%m-%d") == today_str]
            month_sales = sales_df[sales_df["date"].dt.strftime("%Y-%m") == current_month_str]

            if not today_sales.empty:
                if "items_count" in today_sales.columns:
                    today_sales_count = today_sales["items_count"].sum()
                if "total_usd" in today_sales.columns:
                    today_revenue_usd = today_sales["total_usd"].sum()
            
            if not month_sales.empty:
                if "items_count" in month_sales.columns:
                    month_sales_count = month_sales["items_count"].sum()
                if "total_usd" in month_sales.columns:
                    month_revenue_usd = month_sales["total_usd"].sum()

        total_debts_usd = sum(
            agent.get("debt_usd", agent.get("debt", 0.0))
            for agent in factory_data["agents"].values()
            if isinstance(agent, dict)
        )

        st.subheader("📅 ملخص المبيعات والديون")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("برادات اليوم", f"{today_sales_count} براد")
        c2.metric("إيراد اليوم", f"${today_revenue_usd:,.2f}")
        c3.metric("مبيعات الشهر", f"{month_sales_count} براد")
        c4.metric("إيراد الشهر", f"${month_revenue_usd:,.2f}")
        c5.metric("ديون الوكلاء", f"${total_debts_usd:,.2f}")

        st.write("---")
        st.subheader("🧊 المخزون الجاهز من البرادات")
        fg_df = pd.DataFrame(
            list(factory_data.get("finished_goods", {}).items()),
            columns=["نوع البراد", "الكمية المتاحة للبيع"],
        )
        st.dataframe(fg_df, use_container_width=True)

# --- تبويب إدارة الوكلاء والديون ---
tab_agents = tabs[1] if st.session_state.role == "admin" else tabs[1]
with tab_agents:
    st.header("🤝 إدارة الوكلاء وتسديد الديون (بالدولار)")

    sub_ag1, sub_ag2, sub_ag3 = st.tabs([
        "➕ إضافة وكيل جديد",
        "💵 تسديد دين / استلام دفعة",
        "📜 كشف حساب وكيل",
    ])

    with sub_ag1:
        st.subheader("إضافة وكيل جديد")
        ag_name = st.text_input("اسم الوكيل / المحل:")
        ag_phone = st.text_input("رقم الهاتف:")
        ag_initial_debt = st.number_input(
            "الدين السابق ($):",
            min_value=0.0,
            value=0.0,
            step=100.0,
        )

        if st.button("➕ تسجيل الوكيل", type="primary", use_container_width=True):
            if not ag_name.strip():
                st.error("يرجى إدخال اسم الوكيل.")
            elif ag_name in factory_data["agents"]:
                st.error("هذا الوكيل مضاف بالفعل!")
            else:
                factory_data["agents"][ag_name] = {
                    "phone": ag_phone,
                    "debt_usd": ag_initial_debt,
                    "transactions": [],
                }
                if ag_initial_debt > 0:
                    factory_data["agents"][ag_name]["transactions"].append({
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "type": "دين سابق",
                        "amount_usd": ag_initial_debt,
                        "balance_usd": ag_initial_debt,
                        "note": "دين افتتاحي عند التسجيل",
                    })
                save_all_factories(all_factories)
                st.success(f"✅ تم إدخال الوكيل [{ag_name}] بنجاح!")
                st.rerun()

    with sub_ag2:
        st.subheader("تسديد مبلغ من الوكيل (وصل قبض بالدولار)")
        agents_list = list(factory_data["agents"].keys())
        if not agents_list:
            st.info("لا يوجد وكلاء مسجلون حالياً.")
        else:
            selected_ag = st.selectbox("اختر الوكيل:", agents_list, key="pay_agent_select")
            current_debt = factory_data["agents"][selected_ag].get("debt_usd", factory_data["agents"][selected_ag].get("debt", 0.0))
            st.warning(f"💰 الدين الحالي على الوكيل [{selected_ag}]: **${current_debt:,.2f}**")

            pay_amount = st.number_input("المبلغ المدفوع ($):", min_value=0.01, value=100.0, step=50.0)
            exchange_rate = st.number_input("سعر صرف الدولار الحالي (د.ع مقابل كل $1):", min_value=1.0, value=1500.0, step=25.0)
            pay_note = st.text_input("ملاحظات:", value="تسديد دفعة نقدية")

            if st.button("💵 تأكيد القبض وطبع السند", type="primary", use_container_width=True):
                new_debt = current_debt - pay_amount
                factory_data["agents"][selected_ag]["debt_usd"] = new_debt

                receipt_no = factory_data.get("receipt_counter", 1001)
                factory_data["receipt_counter"] = receipt_no + 1

                factory_data["agents"][selected_ag].setdefault("transactions", []).append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": "تسديد دفعة",
                    "amount_usd": -pay_amount,
                    "balance_usd": new_debt,
                    "note": f"وصل قبض #{receipt_no} - {pay_note}",
                })

                save_all_factories(all_factories)

                pdf_bytes = generate_payment_pdf(
                    factory_name=current_factory_name,
                    agent_name=selected_ag,
                    date_str=datetime.now().strftime("%Y-%m-%d"),
                    amount_usd=pay_amount,
                    remaining_debt_usd=new_debt,
                    old_debt_usd=current_debt,
                    exchange_rate=exchange_rate,
                    receipt_no=receipt_no,
                    note=pay_note
                )

                st.success(f"✅ تم الخصم. الدين المتبقي: ${new_debt:,.2f}")
                st.download_button(
                    label="📥 تنزيل سند القبض (PDF)",
                    data=pdf_bytes,
                    file_name=f"سند_قبض_{receipt_no}_{selected_ag}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

    with sub_ag3:
        st.subheader("📜 كشف حساب الوكيل")
        agents_list = list(factory_data["agents"].keys())
        if not agents_list:
            st.info("لا يوجد وكلاء مسجلون.")
        else:
            sel_ag_view = st.selectbox("عرض حساب الوكيل:", agents_list, key="view_agent_select")
            ag_info = factory_data["agents"][sel_ag_view]

            col_a1, col_a2 = st.columns(2)
            col_a1.metric("رقم الهاتف", ag_info.get("phone", "غير محدد"))
            col_a2.metric("صافي الدين الحالي", f"${ag_info.get('debt_usd', ag_info.get('debt', 0)):,.2f}")

            st.write("#### سجل المعاملات:")
            trans_list = ag_info.get("transactions", [])
            formatted_trans = []
            for t in trans_list:
                formatted_trans.append({
                    "التاريخ": t.get("date"),
                    "نوع الحركة": t.get("type"),
                    "المبلغ ($)": f"${t.get('amount_usd', t.get('amount', 0)):,.2f}",
                    "الرصيد بعد الحركة ($)": f"${t.get('balance_usd', t.get('balance', 0)):,.2f}",
                    "ملاحظات": t.get("note", "")
                })
            trans_df = pd.DataFrame(formatted_trans)
            if not trans_df.empty:
                st.dataframe(trans_df, use_container_width=True)
            else:
                st.write("لا توجد معاملات مسجلة.")

# --- تبويب بيع البرادات وإصدار قائمة حساب ---
tab_receipt = tabs[2] if st.session_state.role == "admin" else tabs[0]
with tab_receipt:
    st.header("🛒 بيع البرادات وإصدار قائمة حساب (بالدولار)")

    customer_type = st.radio(
        "نوع المشتري:",
        ["مشتري مباشر (نقداً)", "وكيل مسجل (بالأجل / نقد جزئي)"],
        horizontal=True,
    )

    col_rec1, col_rec2 = st.columns(2)
    with col_rec1:
        if customer_type == "مشتري مباشر (نقداً)":
            customer_name = st.text_input("اسم المشتري:", value="")
            selected_agent_name = None
        else:
            agents_list = list(factory_data["agents"].keys())
            if not agents_list:
                st.warning("⚠️ لا يوجد وكلاء مسجلون!")
                selected_agent_name = None
                customer_name = ""
            else:
                selected_agent_name = st.selectbox("اختر الوكيل:", agents_list)
                customer_name = selected_agent_name
    with col_rec2:
        purchase_date = st.date_input("تاريخ الشراء:", value=datetime.now())

    exchange_rate = st.number_input("سعر صرف الدولار المعتمد في الفاتورة (د.ع مقابل $1):", min_value=1.0, value=1500.0, step=25.0)

    model_list = list(factory_data["bom"].keys())
    if not model_list:
        st.warning("لا توجد أنواع برادات معرفة بالنظام.")
    else:
        selected_items = []
        grand_total_usd, total_units = 0, 0
        stock_error = False

        st.subheader("اختر البرادات المباعة والأسعار بالدولار ($):")
        for model in model_list:
            stock_available = factory_data["finished_goods"].get(model, 0)
            col_m1, col_m2, col_m3 = st.columns([2, 1, 1])
            with col_m1:
                st.write(f"**{model}** (المتوفر: `{stock_available}` براد)")
            with col_m2:
                qty = st.number_input("العدد المباع:", min_value=0, max_value=max(0, stock_available), value=0, key=f"rec_qty_{model}")
            with col_m3:
                price_usd = st.number_input("سعر البراد ($):", min_value=0.0, value=0.0, step=10.0, key=f"rec_price_{model}")

            if qty > stock_available:
                stock_error = True

            if qty > 0:
                total_p_usd = qty * price_usd
                grand_total_usd += total_p_usd
                total_units += qty
                selected_items.append({
                    "model": model,
                    "count": qty,
                    "price_usd": price_usd,
                    "total_usd": total_p_usd,
                })

        grand_total_iqd = grand_total_usd * exchange_rate
        st.markdown(f"### 💰 الإجمالي الكلي: `${grand_total_usd:,.2f}`  /  `{grand_total_iqd:,.0f}` د.ع")

        if customer_type == "وكيل مسجل (بالأجل / نقد جزئي)":
            paid_amount_usd = st.number_input(
                "المبلغ المدفوع نقدياً الآن ($):",
                min_value=0.0,
                max_value=float(grand_total_usd),
                value=float(grand_total_usd),
                step=50.0,
            )
            remaining_amount_usd = grand_total_usd - paid_amount_usd
            st.info(f"المبلغ المضاف على دين الوكيل: **${remaining_amount_usd:,.2f}**")
        else:
            paid_amount_usd = float(grand_total_usd)
            remaining_amount_usd = 0.0

        if st.button("🛒 تأكيد البيع وتوليد قائمة الحساب (PDF)", type="primary", use_container_width=True):
            if stock_error:
                st.error("❌ لا يمكنك بيع عدد أكثر من المخزون المتوفر!")
            elif not customer_name.strip():
                st.error("يرجى إدخال اسم المشتري أو اختيار الوكيل.")
            elif not selected_items:
                st.error("يرجى تحديد كمية براد واحد على الأقل.")
            else:
                receipt_no = factory_data.get("receipt_counter", 1001)

                for item in selected_items:
                    factory_data["finished_goods"][item["model"]] -= item["count"]

                if selected_agent_name and selected_agent_name in factory_data["agents"]:
                    if remaining_amount_usd > 0:
                        old_debt = factory_data["agents"][selected_agent_name].get("debt_usd", factory_data["agents"][selected_agent_name].get("debt", 0.0))
                        new_debt = old_debt + remaining_amount_usd
                        factory_data["agents"][selected_agent_name]["debt_usd"] = new_debt
                        factory_data["agents"][selected_agent_name].setdefault("transactions", []).append({
                            "date": purchase_date.strftime("%Y-%m-%d"),
                            "type": "شراء برادات (متبقي)",
                            "amount_usd": remaining_amount_usd,
                            "balance_usd": new_debt,
                            "note": f"قائمة حساب #{receipt_no}",
                        })

                pdf_bytes = generate_receipt_pdf(
                    factory_name=current_factory_name,
                    customer_name=customer_name,
                    date_str=purchase_date.strftime("%Y-%m-%d"),
                    items_data=selected_items,
                    grand_total_usd=grand_total_usd,
                    paid_amount_usd=paid_amount_usd,
                    remaining_amount_usd=remaining_amount_usd,
                    exchange_rate=exchange_rate,
                    receipt_no=receipt_no,
                )

                factory_data["sales_history"].append({
                    "receipt_no": receipt_no,
                    "date": purchase_date.strftime("%Y-%m-%d"),
                    "customer": customer_name,
                    "items_count": total_units,
                    "total_usd": grand_total_usd,
                    "paid_usd": paid_amount_usd,
                    "remaining_usd": remaining_amount_usd,
                })

                factory_data["receipt_counter"] = receipt_no + 1
                save_all_factories(all_factories)

                st.success("✅ تم تسجيل البيع وترحيل الحساب بنجاح!")
                st.download_button(
                    label="📥 تنزيل قائمة الحساب PDF",
                    data=pdf_bytes,
                    file_name=f"قائمة_حساب_{receipt_no}_{customer_name}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

# --- تبويب تسجيل الإنتاج ---
tab_prod = tabs[3] if st.session_state.role == "admin" else tabs[2]
with tab_prod:
    st.header("🏭 تسجيل عملية إنتاج براد جديد")
    model_list = list(factory_data["bom"].keys())
    if not model_list:
        st.warning("لا توجد أنواع برادات معروفة في النظام.")
    else:
        model = st.selectbox("اختر نموذج البراد المصنوع:", model_list)
        count = st.number_input("عدد البرادات المصنعة:", min_value=1, value=1, step=1)

        if st.button("🚀 خصم المواد الأولية وزيادة البرادات", type="primary", use_container_width=True):
            required_bom = factory_data["bom"][model]
            missing_items = []

            for item, qty in required_bom.items():
                needed = qty * count
                available = factory_data["inventory"].get(item, 0)
                if available < needed:
                    missing_items.append(f"- **{item}**: المطلوب ({needed})، المتوفر ({available})")

            if missing_items:
                st.error("❌ لا يوجد مخزون مواد أولية كافٍ!")
                for m in missing_items:
                    st.write(m)
            else:
                for item, qty in required_bom.items():
                    factory_data["inventory"][item] -= qty * count

                if model not in factory_data["finished_goods"]:
                    factory_data["finished_goods"][model] = 0
                factory_data["finished_goods"][model] += count

                factory_data["production_history"].append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "model": model,
                    "count": count,
                })

                save_all_factories(all_factories)
                st.success(f"✅ تم إنتاج ({count}) من [{model}] بنجاح!")
                st.rerun()

# --- تبويب المخزون ---
tab_inv = tabs[4] if st.session_state.role == "admin" else tabs[3]
with tab_inv:
    if st.session_state.role == "admin":
        st.header("📦 إدارة المخزون")

        st.subheader("🧊 البرادات الجاهزة بالمخزن")
        fg_df = pd.DataFrame(
            list(factory_data["finished_goods"].items()),
            columns=["نوع البراد", "العدد المتوفر للبيع"],
        )
        st.dataframe(fg_df, use_container_width=True)

        st.subheader("🧱 المواد الأولية الخام")
        df = pd.DataFrame(
            list(factory_data["inventory"].items()),
            columns=["اسم المادة الخام", "الكمية المتوفرة"],
        )
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 حفظ التعديلات على المخزون", use_container_width=True):
                new_inv = {}
                for _, row in edited_df.iterrows():
                    if row["اسم المادة الخام"]:
                        new_inv[row["اسم المادة الخام"]] = float(row["الكمية المتوفرة"])
                factory_data["inventory"] = new_inv
                save_all_factories(all_factories)
                st.success("✅ تم تحديث المخزون بنجاح!")
                st.rerun()

        with col_btn2:
            with st.popover("⚠️ تصفير جميع المواد"):
                st.warning("هل أنت متأكد؟ سيتم جعل جميع المواد الأولية (0)!")
                if st.button("نعم، أؤكد التصفير", type="primary", use_container_width=True):
                    for item in factory_data["inventory"]:
                        factory_data["inventory"][item] = 0.0
                    save_all_factories(all_factories)
                    st.success("⚠️ تم التصفير!")
                    st.rerun()
    else:
        st.header("📦 المخزون الحالي")
        st.subheader("🧊 البرادات الجاهزة")
        fg_df = pd.DataFrame(
            list(factory_data["finished_goods"].items()),
            columns=["نوع البراد", "العدد المتوفر للبيع"],
        )
        st.dataframe(fg_df, use_container_width=True)

        st.subheader("🧱 المواد الخام")
        df = pd.DataFrame(
            list(factory_data["inventory"].items()),
            columns=["اسم المادة الخام", "الكمية المتوفرة"],
        )
        st.dataframe(df, use_container_width=True)

# --- تبويبات الإدارة المتقدمة (للمدير فقط) ---
if st.session_state.role == "admin":
    with tabs[5]:
        st.header("👥 إدارة الحسابات والموظفين")

        st.subheader("➕ إضافة حساب موظف/مدير جديد")
        col_u_a1, col_u_a2 = st.columns(2)
        with col_u_a1:
            new_emp_user = st.text_input("اسم المستخدم:")
            new_emp_name = st.text_input("الاسم الثلاثي:")
        with col_u_a2:
            new_emp_pass = st.text_input("كلمة المرور:", type="password")
            new_emp_role = st.selectbox("الصلاحية:", ["staff", "admin"], format_func=lambda x: "👷 موظف" if x == "staff" else "👑 مدير")

        if st.button("➕ إنشاء حساب جديد", type="primary", use_container_width=True):
            if not new_emp_user or not new_emp_pass or not new_emp_name:
                st.error("يرجى ملء كافة الحقول.")
            elif new_emp_user in factory_data["users"]:
                st.error("اسم المستخدم مأخوذ مسبقاً!")
            else:
                factory_data["users"][new_emp_user] = {
                    "password": new_emp_pass,
                    "role": new_emp_role,
                    "name": new_emp_name,
                }
                save_all_factories(all_factories)
                st.success("✅ تم إضافة الحساب بنجاح!")
                st.rerun()

    with tabs[6]:
        st.header("تصدير التقارير إلى Excel")
        df_export = pd.DataFrame(list(factory_data["inventory"].items()), columns=["المادة الخام", "الكمية"])
        df_fg_export = pd.DataFrame(list(factory_data["finished_goods"].items()), columns=["البراد", "العدد"])

        agents_export_data = [{
            "اسم الوكيل": k,
            "رقم الهاتف": v.get("phone", ""),
            "الدين الحالي ($)": v.get("debt_usd", v.get("debt", 0))
        } for k, v in factory_data["agents"].items() if isinstance(v, dict)]
        df_agents_export = pd.DataFrame(agents_export_data)

        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_export.to_excel(writer, index=False, sheet_name="المواد_الخام")
                df_fg_export.to_excel(writer, index=False, sheet_name="البرادات_الجاهزة")
                df_agents_export.to_excel(writer, index=False, sheet_name="ديون_الوكلاء")

            st.download_button(
                label="📥 تنزيل ملف Excel",
                data=buffer.getvalue(),
                file_name=f"تقرير_{current_factory_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception:
            st.error("تأكد من تثبيت مكتبة openpyxl.")

    with tabs[7]:
        st.header("إضافة مادة خام جديدة")
        new_item_name = st.text_input("اسم المادة الخام الجديدة:")
        initial_qty = st.number_input("الكمية الأولية:", min_value=0.0, value=0.0)

        if st.button("➕ إضافة المادة", type="primary", use_container_width=True):
            if new_item_name:
                if new_item_name in factory_data["inventory"]:
                    st.warning("المادة موجودة مسبقاً!")
                else:
                    factory_data["inventory"][new_item_name] = initial_qty
                    save_all_factories(all_factories)
                    st.success("✅ تمت الإضافة بنجاح!")
                    st.rerun()

    with tabs[8]:
        st.header("🛠️ إدارة أنواع البرادات (BOM)")
        model_list = list(factory_data["bom"].keys())
        new_model_name = st.text_input("اسم نموذج البراد الجديد:")
        selected_ingredients = {}

        for item in factory_data["inventory"].keys():
            use_item = st.checkbox(f"يدخل فيه: {item}", key=f"add_chk_{item}")
            if use_item:
                qty_needed = st.number_input(f"الكمية من [{item}]:", min_value=0.1, value=1.0, key=f"add_qty_{item}")
                selected_ingredients[item] = qty_needed

        if st.button("🛠️ حفظ النموذج الجديد", use_container_width=True):
            if new_model_name and selected_ingredients:
                factory_data["bom"][new_model_name] = selected_ingredients
                if new_model_name not in factory_data["finished_goods"]:
                    factory_data["finished_goods"][new_model_name] = 0
                save_all_factories(all_factories)
                st.success("✅ تم حفظ النموذج!")
                st.rerun()
            else:
                st.error("أدخل اسم النموذج ومادة واحدة على الأقل.")

    with tabs[9]:
        st.header("⚠️ فورمات كامل للنظام")
        st.error("تحذير: سيتم حذف جميع البيانات بشكل نهائي!")
        confirm_text = st.text_input("اكتب كلمة (DELETE) للتأكيد:")

        if st.button("🔥 تنفيذ الفورمات", type="primary", use_container_width=True):
            if confirm_text == "DELETE":
                if os.path.exists(DATA_FILE):
                    try:
                        os.remove(DATA_FILE)
                    except Exception:
                        pass
                st.session_state.clear()
                st.success("✅ تم المسح بنجاح!")
                st.rerun()
            else:
                st.error("يجب كتابة (DELETE) بشكل صحيح.")
