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

DATA_FILE = "single_factory_data.json"

# --- 0. دالة التفقيط باللغة العربية ---
def number_to_arabic_words(num):
    if num == 0:
        return "صفر"
    ones = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
    teens = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
    tens_arr = ["", "عشرة", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
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
                    res.append(ones[u] + " و " + tens_arr[t])
                else:
                    res.append(tens_arr[t])
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

# --- 1. هيكل البيانات لمعمل الرافدين ---
def get_default_factory_data():
    return {
        "info": {"factory_name": "معمل الرافدين للبرادات"},
        "users": {
            "admin": {
                "password": "123",
                "role": "admin",
                "name": "المدير",
            }
        },
        "inventory": {
            "الحنفية": {"qty": 50.0, "unit": "قطعة"},
            "البانكة": {"qty": 20.0, "unit": "قطعة"},
            "الماطور": {"qty": 20.0, "unit": "قطعة"},
            "التوماتيك": {"qty": 20.0, "unit": "قطعة"},
            "الطواف": {"qty": 20.0, "unit": "قطعة"},
            "الراديتر": {"qty": 20.0, "unit": "قطعة"},
            "زواية القاعدة": {"qty": 80.0, "unit": "قطعة"},
            "المنيوم القاعدة 1.35m": {"qty": 20.0, "unit": "متر"},
            "الجكنة": {"qty": 20.0, "unit": "قطعة"},
            "واشر حديد": {"qty": 50.0, "unit": "قطعة"},
            "واشر بلاستك": {"qty": 50.0, "unit": "قطعة"},
            "زبانة": {"qty": 20.0, "unit": "قطعة"},
            "كبلري 1.7m": {"qty": 20.0, "unit": "متر"},
            "كويل": {"qty": 20.0, "unit": "قطعة"},
            "بوري ربع 1.5m": {"qty": 20.0, "unit": "متر"},
            "طبقة وربع بليت": {"qty": 30.0, "unit": "وزن"},
        },
        "finished_goods": {
            "براد حنفية واحدة": {"qty": 10, "price": 150.0},
            "براد حنفيتين": {"qty": 10, "price": 180.0},
        },
        "raw_prices": {
            "الحنفية": 5.0, "البانكة": 15.0, "الماطور": 45.0, "التوماتيك": 4.0,
            "الطواف": 3.0, "الراديتر": 25.0, "زواية القاعدة": 2.0, "المنيوم القاعدة 1.35m": 6.0,
            "الجكنة": 10.0, "واشر حديد": 0.5, "واشر بلاستك": 0.5, "زبانة": 3.0,
            "كبلري 1.7m": 4.0, "كويل": 12.0, "بوري ربع 1.5m": 5.0, "طبقة وربع بليت": 20.0,
        },
        "agents": {},
        "bom": {
            "براد حنفية واحدة": {
                "الحنفية": 1, "البانكة": 1, "الماطور": 1, "التوماتيك": 1, "الطواف": 1,
                "الراديتر": 1, "زواية القاعدة": 4, "المنيوم القاعدة 1.35m": 1, "الجكنة": 1,
                "واشر حديد": 1, "واشر بلاستك": 1, "زبانة": 1, "كبلري 1.7m": 1, "كويل": 1,
                "بوري ربع 1.5m": 1, "طبقة وربع بليت": 1.25,
            },
            "براد حنفيتين": {
                "الحنفية": 2, "البانكة": 1, "الماطور": 1, "التوماتيك": 1, "الطواف": 1,
                "الراديتر": 1, "زواية القاعدة": 4, "المنيوم القاعدة 1.35m": 1, "الجكنة": 2,
                "واشر حديد": 2, "واشر بلاستك": 2, "زبانة": 2, "كبلري 1.7m": 1, "كويل": 1,
                "بوري ربع 1.5m": 1, "طبقة وربع بليت": 1.25,
            },
        },
        "receipt_counter": 1001,
        "sales_history": [],
        "production_history": [],
    }

def load_factory_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "users" not in data:
                data["users"] = {"admin": {"password": "123", "role": "admin", "name": "المدير"}}
            return data
        except Exception:
            return get_default_factory_data()
    else:
        d = get_default_factory_data()
        save_factory_data(d)
        return d

def save_factory_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 2. دوال الطباعة والتصدير PDF ---
def ar(text):
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(str(text)))

@st.cache_resource
def ensure_arabic_font():
    font_path = "Amiri-Regular.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"
            res = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(res.content)
        except Exception:
            pass
    return font_path

def generate_new_account_statement_pdf(
    customer_name, customer_type, date_str, items_data, discount_usd,
    grand_total_usd, paid_amount_usd, remaining_amount_usd, exchange_rate, invoice_no, payment_method_str
):
    font_path = ensure_arabic_font()
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    
    pdf.set_y(15)
    if os.path.exists(font_path):
        pdf.add_font("Amiri", "", font_path)
        pdf.set_font("Amiri", "", 14)
    else:
        pdf.set_font("Arial", "B", 12)
        
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, ar("قائمة حساب ومبيعات أو صيانة"), ln=True, align="C")
    pdf.ln(2)
    
    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 10)
    pdf.set_line_width(0.3)
    pdf.cell(93, 6, ar(f"رقم القائمة: {invoice_no}"), border=1, align="R")
    pdf.cell(93, 6, ar(f"التاريخ: {date_str}"), border=1, align="R", ln=True)
    pdf.cell(93, 6, ar(f"اسم العميل / الزبون: {customer_name}"), border=1, align="R")
    pdf.cell(93, 6, ar(f"طريقة الدفع: {payment_method_str}"), border=1, align="R", ln=True)
    pdf.cell(186, 6, ar(f"سعر الصرف المعتمد: {exchange_rate:,.0f} د.ع"), border=1, align="R", ln=True)
    pdf.ln(2)
    
    if items_data:
        col_widths = [46, 45, 25, 40, 30]
        headers = [ar("الصنف"), ar("الإجمالي (د.ع)"), ar("الكمية"), ar("السعر ($)"), ar("الإجمالي ($)")]
        for i, h in enumerate(headers):
            pdf.set_fill_color(240, 245, 250)
            pdf.cell(col_widths[i], 7, h, border=1, align="C", fill=True)
        pdf.ln()
        for item in items_data:
            tot_iqd = item['total_usd'] * exchange_rate
            row_cells = [
                ar(item["model"]),
                f"{tot_iqd:,.0f}",
                str(item["count"]),
                f"${item['price_usd']:,.2f}",
                f"${item['total_usd']:,.2f}"
            ]
            for j, val in enumerate(row_cells):
                pdf.set_fill_color(255, 255, 255)
                pdf.cell(col_widths[j], 6, val, border=1, align="C", fill=True)
            pdf.ln()
            
    gt_iqd = int(round(grand_total_usd * exchange_rate))
    pd_iqd = int(round(paid_amount_usd * exchange_rate))
    rm_iqd = int(round(remaining_amount_usd * exchange_rate))
    disc_iqd = int(round(discount_usd * exchange_rate))
    
    if discount_usd > 0:
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(186, 6, ar(f"قيمة الخصم: ${discount_usd:,.2f} / {disc_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
        
    total_in_words = f"المبلغ الإجمالي وقدره: {number_to_arabic_words(gt_iqd)} دينار عراقي فقط لا غير"
    pdf.set_fill_color(240, 245, 250)
    pdf.cell(186, 6, ar(total_in_words), border=1, align="R", fill=True, ln=True)
    
    pdf.set_fill_color(255, 255, 255)
    pdf.cell(93, 6, ar(f"المبلغ المدفوع: ${paid_amount_usd:,.2f} / {pd_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
    pdf.cell(93, 6, ar(f"المبلغ الإجمالي: ${grand_total_usd:,.2f} / {gt_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
    pdf.set_fill_color(240, 245, 250)
    pdf.cell(186, 6, ar(f"المبلغ المتبقي (الذمة المالية): ${remaining_amount_usd:,.2f} / {rm_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
    
    pdf.ln(4)
    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 10)
    pdf.cell(186, 6, ar("توقيع معمل الرافدين:"), ln=True, align="R")
    sign_box_y = pdf.get_y()
    pdf.rect(12, sign_box_y, 186, 22)
    return bytes(pdf.output())

def generate_payment_pdf(
    agent_name, date_str, amount_usd, remaining_debt_usd, old_debt_usd, exchange_rate, receipt_no, note=""
):
    font_path = ensure_arabic_font()
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    
    pdf.set_y(15)
    if os.path.exists(font_path):
        pdf.add_font("Amiri", "", font_path)
        pdf.set_font("Amiri", "", 14)
    else:
        pdf.set_font("Arial", "B", 12)
        
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, ar("معمل الرافدين للبرادات"), ln=True, align="C")
    pdf.cell(0, 6, ar("سند قبض"), ln=True, align="C")
    pdf.ln(2)
    
    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 10)
    pdf.set_line_width(0.3)
    pdf.cell(93, 6, ar(f"رقم المستند: {receipt_no}"), border=1, align="R")
    pdf.cell(93, 6, ar(f"التاريخ: {date_str}"), border=1, align="R", ln=True)
    pdf.cell(186, 6, ar(f"استلمت من السيد / {agent_name}"), border=1, align="R", ln=True)
    
    amount_iqd = int(round(amount_usd * exchange_rate))
    amount_in_words = f"مبلغ وقدره: {number_to_arabic_words(amount_iqd)} دينار عراقي فقط لا غير"
    pdf.set_fill_color(240, 245, 250)
    pdf.cell(186, 6, ar(amount_in_words), border=1, align="R", fill=True, ln=True)
    
    paid_iqd_val = int(round(amount_usd * exchange_rate))
    pdf.cell(93, 6, ar(f"سعر الصرف: {exchange_rate:,.0f} د.ع"), border=1, align="R", fill=True)
    pdf.cell(93, 6, ar(f"المبلغ المدفوع: ${amount_usd:,.2f} / {paid_iqd_val:,} د.ع"), border=1, align="R", fill=True, ln=True)
    
    note_text = f"الملاحظات: {note}" if note else "الملاحظات: -"
    pdf.set_fill_color(255, 255, 255)
    pdf.cell(186, 6, ar(note_text), border=1, align="R", ln=True)
    
    rem_iqd = int(round(remaining_debt_usd * exchange_rate))
    old_iqd = int(round(old_debt_usd * exchange_rate))
    pdf.set_fill_color(240, 245, 250)
    pdf.cell(186, 6, ar(f"الرصيد السابق: ${old_debt_usd:,.2f} / {old_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
    pdf.cell(186, 6, ar(f"الرصيد بعد التسديد: ${remaining_debt_usd:,.2f} / {rem_iqd:,} د.ع"), border=1, align="R", fill=True, ln=True)
    
    pdf.ln(4)
    pdf.set_font("Amiri" if os.path.exists(font_path) else "Arial", "", 10)
    pdf.cell(186, 6, ar("توقيع وختم القابض:"), ln=True, align="R")
    sign_box_y = pdf.get_y()
    pdf.rect(12, sign_box_y, 186, 22)
    return bytes(pdf.output())

# --- 3. إعداد الصفحة وتصميم الوضع الداكن (Aqua Dark Theme) ---
st.set_page_config(
    page_title="معمل الرافدين للبرادات",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
        background-color: #0b1329;
        color: #e2e8f0;
    }
    
    .stApp {
        background: radial-gradient(circle at 20% 20%, #112244 0%, #0b1329 60%, #070a14 100%);
    }
    
    div.stExpander, div.stTabs, div[data-testid="stForm"], div[data-testid="stVerticalBlock"] > div {
        background-color: rgba(17, 34, 68, 0.6) !important;
        border-radius: 16px !important;
        border: 1px solid rgba(56, 189, 248, 0.2) !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        backdrop-filter: blur(8px);
    }
    
    input, select, textarea, div[data-baseweb="select"] > div {
        background-color: rgba(7, 18, 38, 0.8) !important;
        color: #38bdf8 !important;
        border-radius: 12px !important;
        border: 1px solid rgba(56, 189, 248, 0.4) !important;
    }
    
    input:focus, select:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 15px rgba(56, 189, 248, 0.4) !important;
    }
    
    .stButton>button {
        background: linear-gradient(135deg, #0284c7 0%, #38bdf8 100%);
        color: #ffffff;
        border-radius: 12px;
        font-weight: 700;
        border: none;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3);
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(56, 189, 248, 0.6);
        background: linear-gradient(135deg, #0369a1 0%, #0ea5e9 100%);
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 900;
        color: #38bdf8;
        text-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
    }
    
    div[data-testid="stMetricLabel"] {
        color: #94a3b8;
        font-weight: 600;
    }
    
    h1, h2, h3, h4 {
        color: #f1f5f9 !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
    }
    
    dataframe, table {
        background-color: rgba(11, 19, 41, 0.9) !important;
        color: #cbd5e1 !important;
    }
</style>
""", unsafe_allow_html=True)

factory_data = load_factory_data()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.user_fullname = ""

# --- شاشة تسجيل الدخول ---
if not st.session_state.authenticated:
    st.markdown("<h2 style='text-align: center; color: #38bdf8;'>💧 نظام إدارة معمل الرافدين</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94a3b8;'>يرجى تسجيل الدخول للمتابعة</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username_input = st.text_input("اسم المستخدم:")
            password_input = st.text_input("كلمة المرور:", type="password")
            submit_login = st.form_submit_button("تسجيل الدخول", use_container_width=True)
            
            if submit_login:
                users_dict = factory_data.get("users", {})
                if username_input in users_dict and users_dict[username_input]["password"] == password_input:
                    st.session_state.authenticated = True
                    st.session_state.username = username_input
                    st.session_state.role = users_dict[username_input]["role"]
                    st.session_state.user_fullname = users_dict[username_input]["name"]
                    st.success("✅ تم تسجيل الدخول بنجاح!")
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة!")
    st.stop()

# --- الواجهة الرئيسية والشريط العلوي ---
st.markdown(f"<h1 style='text-align: center; color: #38bdf8;'>💧 {factory_data['info']['factory_name']}</h1>", unsafe_allow_html=True)

col_u1, col_u2 = st.columns([4, 1])
with col_u1:
    role_badge = "👑 مدير" if st.session_state.role == "admin" else "👷 موظف"
    st.markdown(f"**المستخدم الحالي:** `{st.session_state.user_fullname}` | **الصلاحية:** {role_badge}")
with col_u2:
    if st.button("🚪 خروج", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.username = None
        st.rerun()

st.markdown("---")

# --- التبويبات الرئيسية ---
if st.session_state.role == "admin":
    tabs = st.tabs([
        "📊 التقارير",
        "🤝 الوكلاء",
        "🛒 البيع",
        "🛠️ الصيانة والمواد الخام",
        "🏭 الإنتاج",
        "📦 المخزون",
        "👥 الحسابات",
        "⚙️ الإعدادات",
        "⚠️ فورمات",
    ])
else:
    tabs = st.tabs([
        "🛒 البيع",
        "🛠️ الصيانة والمواد الخام",
        "🤝 الوكلاء",
        "🏭 الإنتاج",
        "📦 المخزون",
        "⚙️ الإعدادات",
    ])

# --- 1. التقارير الشاملة (مدير فقط) ---
if st.session_state.role == "admin":
    with tabs[0]:
        st.header("📊 التقارير الشاملة")
        today_str = datetime.now().strftime("%Y-%m-%d")
        sales_history = factory_data.get("sales_history", [])
        today_rev = sum(s.get("total_usd", 0) for s in sales_history if s.get("date") == today_str)
        total_debts = sum(ag.get("debt_usd", 0) for ag in factory_data["agents"].values() if isinstance(ag, dict))
        
        c1, c2, c3 = st.columns(3)
        c1.metric("إيرادات مبيعات اليوم", f"${today_rev:,.2f}")
        c2.metric("إجمالي ديون الذمم", f"${total_debts:,.2f}")
        c3.metric("إجمالي عمليات البيع", f"{len(sales_history)} عملية")
        
        st.markdown("---")
        st.subheader("🧊 المخزون الجاهز")
        fg_list = [{"البراد": k, "العدد": v["qty"], "السعر الثابت ($)": v["price"]} for k, v in factory_data["finished_goods"].items()]
        st.dataframe(pd.DataFrame(fg_list), use_container_width=True)

# --- إدارة الوكلاء والديون ---
tab_ag_idx = 1 if st.session_state.role == "admin" else 2
with tabs[tab_ag_idx]:
    st.header("🤝 إدارة الوكلاء والذمم")
    ag_sub1, ag_sub2, ag_sub3 = st.tabs(["➕ إضافة وكيل", "💵 سند قبض", "📜 كشف الحساب"])
    
    with ag_sub1:
        st.subheader("إضافة وكيل أو زبون جديد")
        with st.form("add_agent_form"):
            ag_name = st.text_input("اسم الوكيل / الزبون:")
            ag_phone = st.text_input("رقم الهاتف:")
            ag_init_debt = st.number_input("الرصيد / الدين السابق ($):", min_value=0.0, value=0.0, step=50.0)
            submit_ag = st.form_submit_button("➕ تسجيل الوكيل", use_container_width=True)
            
            if submit_ag:
                if not ag_name.strip():
                    st.error("يرجى إدخال اسم الوكيل.")
                elif ag_name in factory_data["agents"]:
                    st.error("هذا الوكيل مسجل مسبقاً!")
                else:
                    factory_data["agents"][ag_name] = {
                        "phone": ag_phone,
                        "debt_usd": ag_init_debt,
                        "transactions": []
                    }
                    if ag_init_debt > 0:
                        factory_data["agents"][ag_name]["transactions"].append({
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "type": "دين سابق",
                            "amount_usd": ag_init_debt,
                            "balance_usd": ag_init_debt,
                            "note": "رصيد افتتاحى"
                        })
                    save_factory_data(factory_data)
                    st.success(f"✅ تم إضافة الوكيل [{ag_name}] بنجاح وتم حفظ البيانات!")

    with ag_sub2:
        st.subheader("تسديد دفعة نقدية (سند قبض)")
        agents_list = list(factory_data["agents"].keys())
        if not agents_list:
            st.info("لا توجد حسابات وكلاء مسجلة حالياً.")
        else:
            sel_agent = st.selectbox("اختر الوكيل / الزبون:", agents_list, key="pay_agent_select")
            cur_debt = factory_data["agents"][sel_agent].get("debt_usd", 0.0)
            st.info(f"الذمة المالية الحالية على [{sel_agent}]: **${cur_debt:,.2f}**")
            
            pay_amt = st.number_input("المبلغ المدفوع ($):", min_value=0.01, value=100.0, step=25.0, key="pay_amount_input")
            ex_rate = st.number_input("سعر صرف الدولار (د.ع):", min_value=1.0, value=1500.0, step=25.0, key="pay_rate_input")
            pay_note = st.text_input("ملاحظات السند:", value="تسديد نقدآ", key="pay_note_input")
            
            submit_pay = st.button("💵 تأكيد القبض وطباعة السند", type="primary", use_container_width=True, key="pay_submit_btn")
            
            if submit_pay:
                new_debt = cur_debt - pay_amt
                factory_data["agents"][sel_agent]["debt_usd"] = new_debt
                receipt_no = factory_data.get("receipt_counter", 1001)
                factory_data["receipt_counter"] = receipt_no + 1
                factory_data["agents"][sel_agent].setdefault("transactions", []).append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": "تسديد",
                    "amount_usd": -pay_amt,
                    "balance_usd": new_debt,
                    "note": f"سند قبض #{receipt_no}"
                })
                save_factory_data(factory_data)
                st.success("✅ تم إتمام سند القبض وتحديث الحساب بنجاح!")
                
                pdf_bytes = generate_payment_pdf(
                    agent_name=sel_agent,
                    date_str=datetime.now().strftime("%Y-%m-%d"),
                    amount_usd=pay_amt,
                    remaining_debt_usd=new_debt,
                    old_debt_usd=cur_debt,
                    exchange_rate=ex_rate,
                    receipt_no=receipt_no,
                    note=pay_note
                )
                st.download_button(
                    label="📥 تنزيل سند القبض (PDF)",
                    data=pdf_bytes,
                    file_name=f"سند_قبض_{receipt_no}_{sel_agent}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    with ag_sub3:
        st.subheader("كشف الحساب التفصيلي")
        if not agents_list:
            st.info("لا توجد بيانات وكلاء.")
        else:
            v_ag = st.selectbox("اختر الوكيل للعرض:", agents_list, key="view_ag_box")
            ag_data = factory_data["agents"][v_ag]
            st.metric("صافي الذمة المالية", f"${ag_data.get('debt_usd', 0.0):,.2f}")
            trans = ag_data.get("transactions", [])
            if trans:
                st.dataframe(pd.DataFrame(trans), use_container_width=True)
            else:
                st.write("لا توجد حركات مسجلة لهذا الحساب.")

# --- نافذة البيع ---
tab_sale_idx = 2 if st.session_state.role == "admin" else 0
with tabs[tab_sale_idx]:
    st.header("🛒 نافذة البيع (البرادات الجاهزة)")
    buyer_category = st.radio("تصنيف المشتري:", ["زبون مباشر", "وكيل مسجل"], horizontal=True, key="sale_buyer_cat")
    
    agents_list = list(factory_data["agents"].keys())
    if buyer_category == "وكيل مسجل":
        if not agents_list:
            st.warning("⚠️ لا يوجد وكلاء مسجلون! قم بإضافتهم من تبويب الوكلاء.")
            selected_agent_key = None
            customer_display_name = ""
        else:
            selected_agent_key = st.selectbox("اختر الوكيل:", agents_list, key="sale_agent_select")
            customer_display_name = selected_agent_key
    else:
        customer_display_name = st.text_input("اسم الزبون المباشر:", value="زبون نقدي", key="sale_direct_customer")
        selected_agent_key = None

    payment_system = st.selectbox(
        "طريقة البيع وسداد المبلغ:",
        ["بيع نقدي بالكامل", "بيع بالأجل (على الذمة)", "بيع بالتقساط (دفعة مقدمة + أقساط متبقية)"],
        key="sale_payment_system"
    )
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        purchase_date = st.date_input("تاريخ العملية:", value=datetime.now(), key="sale_date_input")
    with col_s2:
        exchange_rate = st.number_input("سعر صرف الدولار (د.ع):", min_value=1.0, value=1500.0, step=25.0, key="sale_exchange_rate")
        
    st.markdown("---")
    selected_items_list = []
    total_invoice_usd = 0.0
    stock_shortage = False
    
    st.subheader("🧊 اختيار البرادات")
    bom_models = list(factory_data["finished_goods"].keys())
    for model_name in bom_models:
        fg_info = factory_data["finished_goods"][model_name]
        available_qty = fg_info["qty"]
        fixed_price = fg_info["price"]
        
        c_m1, c_m2, c_m3 = st.columns([2, 1, 1])
        with c_m1:
            st.markdown(f"**{model_name}** | المتوفر: `{available_qty}` | السعر: `${fixed_price}`")
        with c_m2:
            qty_bought = st.number_input("الكمية:", min_value=0, max_value=max(0, available_qty), value=0, key=f"sale_qty_{model_name}")
        with c_m3:
            unit_price_usd = st.number_input("السعر ($):", min_value=0.0, value=float(fixed_price), step=10.0, key=f"sale_pr_{model_name}")
            
        if qty_bought > available_qty:
            stock_shortage = True
        if qty_bought > 0:
            item_tot = qty_bought * unit_price_usd
            total_invoice_usd += item_tot
            selected_items_list.append({
                "model": model_name,
                "count": qty_bought,
                "type": "finished",
                "price_usd": unit_price_usd,
                "total_usd": item_tot
            })

    discount_usd = st.number_input("قيمة الخصم (تخفيض) على الإجمالي ($):", min_value=0.0, value=0.0, step=5.0, key="sale_discount_input")
    final_invoice_usd = max(0.0, total_invoice_usd - discount_usd)
    st.markdown(f"### 💰 إجمالي الفاتورة بعد الخصم: `${final_invoice_usd:,.2f}` (`{final_invoice_usd * exchange_rate:,.0f}` د.ع)")
    
    paid_now_usd = 0.0
    remaining_debt_usd = 0.0
    installments_note = ""
    if payment_system == "بيع نقدي بالكامل":
        paid_now_usd = final_invoice_usd
        remaining_debt_usd = 0.0
        payment_desc_str = "نقدي بالكامل"
    elif payment_system == "بيع بالأجل (على الذمة)":
        paid_now_usd = 0.0
        remaining_debt_usd = final_invoice_usd
        payment_desc_str = "بيع بالأجل"
    else:
        paid_now_usd = st.number_input("المقدمة المدفوعة الآن ($):", min_value=0.0, max_value=float(final_invoice_usd), value=0.0, step=25.0, key="sale_paid_input")
        remaining_debt_usd = final_invoice_usd - paid_now_usd
        installments_note = st.text_input("تفاصيل جدول الأقساط:", value="أقساط شهرية متفق عليها", key="sale_installments_note")
        payment_desc_str = f"تقساط (مقدمة: ${paid_now_usd:,.2f})"

    if st.button("🚀 إتمام البيع وتوليد قائمة الحساب", type="primary", use_container_width=True, key="sale_submit_btn"):
        if stock_shortage:
            st.error("❌ الكمية المطلوبة تتجاوز المخزون المتوفر!")
        elif not customer_display_name.strip():
            st.error("❌ يرجى إدخال اسم العميل.")
        elif not selected_items_list:
            st.error("❌ يرجى اختيار صنف واحد على الأقل.")
        else:
            invoice_seq = factory_data.get("receipt_counter", 1001)
            factory_data["receipt_counter"] = invoice_seq + 1
            for item in selected_items_list:
                if item["type"] == "finished":
                    factory_data["finished_goods"][item["model"]]["qty"] -= item["count"]
                    
            if remaining_debt_usd > 0:
                target_ag = selected_agent_key if (selected_agent_key and selected_agent_key in factory_data["agents"]) else customer_display_name
                if target_ag not in factory_data["agents"]:
                    factory_data["agents"][target_ag] = {"phone": "مباشر", "debt_usd": 0.0, "transactions": []}
                old_d = factory_data["agents"][target_ag].get("debt_usd", 0.0)
                new_d = old_d + remaining_debt_usd
                factory_data["agents"][target_ag]["debt_usd"] = new_d
                factory_data["agents"][target_ag]["transactions"].append({
                    "date": purchase_date.strftime("%Y-%m-%d"),
                    "type": payment_system,
                    "amount_usd": remaining_debt_usd,
                    "balance_usd": new_d,
                    "note": f"قائمة حساب #{invoice_seq} - {installments_note}"
                })
                
            factory_data["sales_history"].append({
                "invoice_no": invoice_seq,
                "date": purchase_date.strftime("%Y-%m-%d"),
                "customer": customer_display_name,
                "total_usd": final_invoice_usd,
                "payment_type": payment_desc_str
            })
            save_factory_data(factory_data)
            st.success("✅ تمت عملية البيع وتأكيد إتمام المهمة بنجاح وتم خصم المخزون!")
            
            pdf_bytes = generate_new_account_statement_pdf(
                customer_name=customer_display_name,
                customer_type=buyer_category,
                date_str=purchase_date.strftime("%Y-%m-%d"),
                items_data=selected_items_list,
                discount_usd=discount_usd,
                grand_total_usd=final_invoice_usd,
                paid_amount_usd=paid_now_usd,
                remaining_amount_usd=remaining_debt_usd,
                exchange_rate=exchange_rate,
                invoice_no=invoice_seq,
                payment_method_str=payment_desc_str
            )
            st.download_button(
                label="📥 تنزيل قائمة الحساب (PDF)",
                data=pdf_bytes,
                file_name=f"قائمة_حساب_{invoice_seq}_{customer_display_name}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# --- 4. تبويب الصيانة والمواد الخام (المدمج) ---
tab_maint_raw_idx = 3 if st.session_state.role == "admin" else 1
with tabs[tab_maint_raw_idx]:
    st.header("🛠️ قسم الصيانة وبيع المواد الخام")
    st.write("حدد أجور الصيانة ووصف الأعطال، واختر المواد الخام المستهلكة أو المباعة لتظهر معاً في وصل واحد.")
    
    m_buyer_cat = st.radio("تصنيف العميل:", ["زبون مباشر", "وكيل مسجل"], horizontal=True, key="maint_cat_radio_combined")
    m_agents_list = list(factory_data["agents"].keys())
    
    if m_buyer_cat == "وكيل مسجل":
        if not m_agents_list:
            st.warning("⚠️ لا توجد وكلاء مسجلون!")
            m_customer_name = ""
            m_sel_agent = None
        else:
            m_sel_agent = st.selectbox("اختر الوكيل:", m_agents_list, key="maint_agent_select_combined")
            m_customer_name = m_sel_agent
    else:
        m_customer_name = st.text_input("اسم الزبون:", value="زبون نقدي", key="maint_direct_customer_combined")
        m_sel_agent = None
        
    m_pay_sys = st.selectbox("طريقة السداد:", ["نقدي بالكامل", "بالأجل (على الذمة)", "بالتقساط"], key="maint_pay_sys_combined")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        m_date = st.date_input("تاريخ العملية:", value=datetime.now(), key="maint_date_input_combined")
    with col_m2:
        m_ex = st.number_input("سعر صرف الدولار (د.ع):", min_value=1.0, value=1500.0, step=25.0, key="maint_exchange_rate_combined")
        
    st.markdown("---")
    
    # تبويبان فرعيان داخل التبويب المدمج
    sub_tab_1, sub_tab_2 = st.tabs(["📋 1. أجور الصيانة وتحديد العطل", "🧱 2. المواد الخام المستهلكة أو المباعة"])
    
    m_items_list = []
    m_total_usd = 0.0
    m_stock_shortage = False
    
    with sub_tab_1:
        st.subheader("إدخال تفاصيل وأجور الصيانة")
        maint_desc = st.text_input("وصف العطل أو الإصلاح:", value="إصلاح عطل فني في البراد", key="maint_desc_input_combined")
        mc1, mc2 = st.columns(2)
        with mc1:
            maint_cnt = st.number_input("العدد / الساعات:", min_value=0, value=1, step=1, key="maint_cnt_input_combined")
        with mc2:
            maint_p = st.number_input("أجور الصيانة ($):", min_value=0.0, value=0.0, step=5.0, key="maint_price_input_combined")
            
        if maint_cnt > 0 and maint_p > 0:
            mt_tot = maint_cnt * maint_p
            m_total_usd += mt_tot
            m_items_list.append({
                "model": f"صيانة: {maint_desc}",
                "count": maint_cnt,
                "type": "maintenance",
                "price_usd": maint_p,
                "total_usd": mt_tot
            })

    with sub_tab_2:
        st.subheader("اختر المواد الخام (التي استهلكت بالصيانة أو بيعت مفردة)")
        raw_inv = factory_data.get("inventory", {})
        raw_pr = factory_data.get("raw_prices", {})
        
        for r_name, r_info in raw_inv.items():
            r_avail = r_info["qty"]
            r_unit = r_info["unit"]
            r_fixed_p = raw_pr.get(r_name, 5.0)
            
            with st.container():
                rc1, rc2, rc3 = st.columns([2, 1, 1])
                with rc1:
                    st.markdown(f"**{r_name}** | متوفر: `{r_avail} {r_unit}` | السعر: `${r_fixed_p}`")
                with rc2:
                    r_qty = st.number_input("الكمية:", min_value=0.0, max_value=float(r_avail), value=0.0, step=1.0, key=f"raw_q_comb_{r_name}")
                with rc3:
                    r_pr = st.number_input("السعر ($):", min_value=0.0, value=float(r_fixed_p), step=1.0, key=f"raw_p_comb_{r_name}")
                st.markdown("<div style='margin-bottom: 5px;'></div>", unsafe_allow_html=True)
                
            if r_qty > r_avail:
                m_stock_shortage = True
            if r_qty > 0:
                rt = r_qty * r_pr
                m_total_usd += rt
                m_items_list.append({
                    "model": r_name,
                    "count": r_qty,
                    "type": "raw",
                    "raw_name": r_name,
                    "price_usd": r_pr,
                    "total_usd": rt
                })

    st.markdown("---")
    m_discount = st.number_input("قيمة الخصم الكلي ($):", min_value=0.0, value=0.0, step=5.0, key="m_disc_combined")
    m_final_usd = max(0.0, m_total_usd - m_discount)
    st.markdown(f"### 💰 إجمالي الوصل الموحد بعد الخصم: `${m_final_usd:,.2f}` (`{m_final_usd * m_ex:,.0f}` د.ع)")
    
    m_paid = 0.0
    m_rem = 0.0
    if m_pay_sys == "نقدي بالكامل":
        m_paid = m_final_usd
        m_rem = 0.0
        m_pay_desc = "نقدي"
    elif m_pay_sys == "بالأجل (على الذمة)":
        m_paid = 0.0
        m_rem = m_final_usd
        m_pay_desc = "أجل"
    else:
        m_paid = st.number_input("المقدمة المدفوعة ($):", min_value=0.0, max_value=float(m_final_usd), value=0.0, step=10.0, key="maint_paid_input_combined")
        m_rem = m_final_usd - m_paid
        m_pay_desc = f"تقساط (مقدمة: ${m_paid})"

    if st.button("🚀 إتمام وتنفيذ وطباعة الوصل الموحد", type="primary", use_container_width=True, key="maint_submit_btn_combined"):
        if m_stock_shortage:
            st.error("❌ الكمية المطلوبة من المواد الخام تتجاوز المخزون المتوفر!")
        elif not m_customer_name.strip():
            st.error("❌ يرجى إدخال اسم العميل.")
        elif not m_items_list:
            st.error("❌ يرجى إضافة أجور صيانة أو اختيار مادة خام واحدة على الأقل.")
        else:
            m_inv_seq = factory_data.get("receipt_counter", 1001)
            factory_data["receipt_counter"] = m_inv_seq + 1
            
            # خصم المواد الخام المستخدمة أو المباعة من المخزون
            for itm in m_items_list:
                if itm["type"] == "raw":
                    factory_data["inventory"][itm["raw_name"]]["qty"] -= itm["count"]
                    
            if m_rem > 0:
                target_ag = m_sel_agent if (m_sel_agent and m_sel_agent in factory_data["agents"]) else m_customer_name
                if target_ag not in factory_data["agents"]:
                    factory_data["agents"][target_ag] = {"phone": "مباشر", "debt_usd": 0.0, "transactions": []}
                old_d = factory_data["agents"][target_ag].get("debt_usd", 0.0)
                new_d = old_d + m_rem
                factory_data["agents"][target_ag]["debt_usd"] = new_d
                factory_data["agents"][target_ag]["transactions"].append({
                    "date": m_date.strftime("%Y-%m-%d"),
                    "type": f"صيانة ومواد خام - {m_pay_sys}",
                    "amount_usd": m_rem,
                    "balance_usd": new_d,
                    "note": f"قائمة #{m_inv_seq}"
                })
                
            factory_data["sales_history"].append({
                "invoice_no": m_inv_seq,
                "date": m_date.strftime("%Y-%m-%d"),
                "customer": m_customer_name,
                "total_usd": m_final_usd,
                "payment_type": m_pay_desc
            })
            save_factory_data(factory_data)
            st.success(f"✅ تمت العملية بنجاح وتوليد الوصل الموحد برقم #{m_inv_seq} وتحديث المخزون!")
            
            pdf_bytes = generate_new_account_statement_pdf(
                customer_name=m_customer_name,
                customer_type=m_buyer_cat,
                date_str=m_date.strftime("%Y-%m-%d"),
                items_data=m_items_list,
                discount_usd=m_discount,
                grand_total_usd=m_final_usd,
                paid_amount_usd=m_paid,
                remaining_amount_usd=m_rem,
                exchange_rate=m_ex,
                invoice_no=m_inv_seq,
                payment_method_str=m_pay_desc
            )
            st.download_button(
                label="📥 تنزيل الوصل الموحد (PDF)",
                data=pdf_bytes,
                file_name=f"وصل_صيانة_{m_inv_seq}_{m_customer_name}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# --- تسجيل الإنتاج ---
tab_prod_idx = 4 if st.session_state.role == "admin" else 3
with tabs[tab_prod_idx]:
    st.header("🏭 تسجيل إنتاج براد جديد")
    models = list(factory_data["bom"].keys())
    if models:
        with st.form("production_form"):
            prod_model = st.selectbox("اختر البراد المراد إنتاجه:", models, key="prod_model_select")
            prod_qty = st.number_input("العدد المصنوع:", min_value=1, value=1, step=1, key="prod_qty_input")
            submit_prod = st.form_submit_button("🚀 خصم المواد الخام وإضافة البرادات", use_container_width=True)
            
            if submit_prod:
                bom_req = factory_data["bom"][prod_model]
                missing = []
                for mat, req_val in bom_req.items():
                    needed = req_val * prod_qty
                    avail = factory_data["inventory"].get(mat, {}).get("qty", 0.0)
                    if avail < needed:
                        missing.append(f"- {mat}: المطلوب ({needed})، المتوفر ({avail})")
                if missing:
                    st.error("❌ المواد الخام غير كافية بالمخزن:")
                    for m in missing:
                        st.write(m)
                else:
                    for mat, req_val in bom_req.items():
                        factory_data["inventory"][mat]["qty"] -= req_val * prod_qty
                    factory_data["finished_goods"][prod_model]["qty"] += prod_qty
                    save_factory_data(factory_data)
                    st.success(f"✅ تم تأكيد الإنتاج بنجاح ({prod_qty}) من [{prod_model}] وخصم المواد الخام تلقائياً!")

# --- إدارة المخزون ---
tab_inv_idx = 5 if st.session_state.role == "admin" else 4
with tabs[tab_inv_idx]:
    if st.session_state.role == "admin":
        st.header("📦 إدارة المخزون")
        inv_sub1, inv_sub2, inv_sub3, inv_sub4 = st.tabs(["➕ إضافة / تزويد مخزون", "➕ صنف جديد", "📦 المواد الحالية", "⚠️ تعديل وحذف"])
        
        with inv_sub1:
            st.subheader("إضافة كمية جديدة للمخزون الخام")
            inv_names_list = list(factory_data["inventory"].keys())
            if inv_names_list:
                with st.form("add_stock_form"):
                    sel_add_mat = st.selectbox("اختر المادة الخام:", inv_names_list, key="inv_add_mat_select")
                    current_q = factory_data["inventory"][sel_add_mat]["qty"]
                    current_u = factory_data["inventory"][sel_add_mat]["unit"]
                    st.info(f"الكمية الحالية المتوفرة لـ [{sel_add_mat}]: `{current_q}` ({current_u})")
                    
                    added_q = st.number_input("العدد / الكمية المراد إضافتها:", min_value=0.0, value=10.0, step=1.0, key="inv_added_qty_input")
                    submit_add_stock = st.form_submit_button("➕ تزويد المخزون وجمعها تلقائياً", use_container_width=True)
                    
                    if submit_add_stock:
                        factory_data["inventory"][sel_add_mat]["qty"] += added_q
                        save_factory_data(factory_data)
                        st.success(f"✅ تم إضافة ({added_q}) إلى [{sel_add_mat}] بنجاح وأصبح الإجمالي: `{factory_data['inventory'][sel_add_mat]['qty']}`!")
                        
        with inv_sub2:
            st.subheader("إضافة صنف مادة خام جديدة تماماً")
            with st.form("new_mat_form"):
                new_mat_name = st.text_input("اسم المادة الخام الجديدة:", key="new_mat_name_input")
                new_mat_unit = st.selectbox("وحدة القياس:", ["قطعة", "متر", "وزن"], key="new_mat_unit_select")
                new_mat_qty = st.number_input("الكمية الأولية:", min_value=0.0, value=0.0, step=1.0, key="new_mat_qty_input")
                new_mat_price = st.number_input("السعر الثابت الافتراضي ($):", min_value=0.0, value=5.0, step=1.0, key="new_mat_price_input")
                submit_new_mat = st.form_submit_button("➕ حفظ الصنف الجديد", use_container_width=True)
                
                if submit_new_mat:
                    if not new_mat_name.strip():
                        st.error("❌ يرجى إدخال اسم المادة.")
                    elif new_mat_name in factory_data["inventory"]:
                        st.error("❌ هذه المادة مسجلة مسبقاً!")
                    else:
                        factory_data["inventory"][new_mat_name] = {"qty": new_mat_qty, "unit": new_mat_unit}
                        factory_data["raw_prices"][new_mat_name] = new_mat_price
                        save_factory_data(factory_data)
                        st.success(f"✅ تم إضافة الصنف الجديد [{new_mat_name}] بنجاح!")
                        
        with inv_sub3:
            st.subheader("المواد الخام وبرادات المعمل الحالية")
            raw_display_list = [{"المادة الخام": k, "الكمية": v["qty"], "الوحدة": v["unit"], "السعر الثابت ($)": factory_data.get("raw_prices", {}).get(k, 5.0)} for k, v in factory_data["inventory"].items()]
            st.dataframe(pd.DataFrame(raw_display_list), use_container_width=True)
            
            fg_display_list = [{"البراد": k, "الكمية": v["qty"], "السعر الثابت ($)": v["price"]} for k, v in factory_data["finished_goods"].items()]
            st.dataframe(pd.DataFrame(fg_display_list), use_container_width=True)
            
        with inv_sub4:
            st.subheader("تعديل أو حذف مواد خام")
            ed_mat_list = list(factory_data["inventory"].keys())
            if ed_mat_list:
                target_del_mat = st.selectbox("اختر المادة الخام لإدارتها:", ed_mat_list, key="inv_del_mat_select")
                with st.popover("⚠️ حذف هذه المادة الخام نهائياً"):
                    st.warning(f"هل أنت متأكد من حذف المادة [{target_del_mat}]؟")
                    chk_del_word = st.text_input("اكتب كلمة (حذف) للتأكيد:", key="inv_del_confirm_input")
                    if st.button("تأكيد الحذف النهائي", type="primary", key="inv_del_final_btn"):
                        if chk_del_word == "حذف":
                            del factory_data["inventory"][target_del_mat]
                            if target_del_mat in factory_data["raw_prices"]:
                                del factory_data["raw_prices"][target_del_mat]
                            save_factory_data(factory_data)
                            st.success("✅ تم حذف المادة الخام بنجاح وتأكيد الإجراء.")
                        else:
                            st.error("❌ يرجى كتابة كلمة (حذف) بدقة لتأكيد العملية.")
    else:
        st.header("📦 عرض المخزون")
        raw_display_list = [{"المادة الخام": k, "الكمية": v["qty"], "الوحدة": v["unit"]} for k, v in factory_data["inventory"].items()]
        st.dataframe(pd.DataFrame(raw_display_list), use_container_width=True)
        fg_display_list = [{"البراد": k, "الكمية": v["qty"]} for k, v in factory_data["finished_goods"].items()]
        st.dataframe(pd.DataFrame(fg_display_list), use_container_width=True)

# --- الحسابات والموظفين (مدير فقط) ---
if st.session_state.role == "admin":
    with tabs[6]:
        st.header("👥 إدارة الحسابات والموظفين")
        with st.form("new_user_form"):
            u_name = st.text_input("اسم المستخدم:", key="new_user_name_input")
            u_full = st.text_input("الاسم الكامل:", key="new_user_fullname_input")
            u_pass = st.text_input("كلمة المرور:", type="password", key="new_user_pass_input")
            u_role = st.selectbox("الصلاحية:", ["staff", "admin"], format_func=lambda x: "مشرف / مدير" if x == "admin" else "موظف عادي", key="new_user_role_select")
            submit_user = st.form_submit_button("➕ إنشاء الحساب", use_container_width=True)
            
            if submit_user:
                if u_name and u_pass:
                    if u_name in factory_data["users"]:
                        st.error("❌ اسم المستخدم موجود مسبقاً!")
                    else:
                        factory_data["users"][u_name] = {"password": u_pass, "role": u_role, "name": u_full}
                        save_factory_data(factory_data)
                        st.success("✅ تم إنشاء حساب الموظف بنجاح!")

# --- إعدادات الحساب الشخصي ---
tab_set_idx = 7 if st.session_state.role == "admin" else 5
with tabs[tab_set_idx]:
    st.header("⚙️ إعدادات الحساب الشخصي")
    current_username = st.session_state.username
    with st.form("settings_form"):
        new_username_input = st.text_input("اسم المستخدم الجديد:", value=current_username, key="set_username_input")
        new_password_input = st.text_input("كلمة المرور الجديدة:", type="password", key="set_pass_input")
        confirm_password_input = st.text_input("تأكيد كلمة المرور الجديدة:", type="password", key="set_confirm_pass_input")
        submit_settings = st.form_submit_button("💾 حفظ التعديلات الشخصية", use_container_width=True)
        
        if submit_settings:
            if not new_username_input.strip():
                st.error("❌ اسم المستخدم لا يمكن أن يكون فارغاً.")
            elif new_password_input and new_password_input != confirm_password_input:
                st.error("❌ كلمتا المرور غير متطابقتين!")
            else:
                if new_username_input != current_username:
                    if new_username_input in factory_data["users"]:
                        st.error("❌ اسم المستخدم هذا مستخدم بالفعل من قبل شخص آخر!")
                        st.stop()
                    factory_data["users"][new_username_input] = factory_data["users"].pop(current_username)
                    st.session_state.username = new_username_input
                if new_password_input:
                    factory_data["users"][st.session_state.username]["password"] = new_password_input
                save_factory_data(factory_data)
                st.success("✅ تم تحديث بيانات الحساب الشخصي وحفظ الإجراء بنجاح!")

# --- فورمات كامل للمدير ---
if st.session_state.role == "admin":
    with tabs[8]:
        st.header("⚠️ فورمات كامل للنظام")
        st.error("تحذير صارم: سيؤدي هذا لتصفير وحذف جميع البيانات نهائياً!")
        with st.form("format_form"):
            conf_word = st.text_input("اكتب كلمة (DELETE) للتأكيد:", key="format_confirm_input")
            submit_format = st.form_submit_button("🔥 تنفيذ الفورمات الكامل", use_container_width=True)
            
            if submit_format:
                if conf_word == "DELETE":
                    if os.path.exists(DATA_FILE):
                        os.remove(DATA_FILE)
                    st.session_state.clear()
                    st.success("✅ تم فورمات النظام وإعادة تهيئته بنجاح.")
                    st.rerun()
                else:
                    st.error("❌ يجب كتابة كلمة (DELETE) بدقة لتأكيد عملية الفورمات.")
