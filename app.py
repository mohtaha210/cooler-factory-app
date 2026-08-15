import streamlit as st
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# إعداد الصفحة لتكون ملائمة للموبايل وتدعم اللغة العربية
st.set_page_config(page_title="معمل الرافدين للمبردات", layout="centered")

# إعداد قاعدة البيانات داخل بيئة Streamlit
db_file = "alrafidain.db"
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# جدول العمليات والصيانة
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), default="عميل عام")
    maint_desc = db.Column(db.String(200))
    maint_price = db.Column(db.Float, default=0.0)
    item_name = db.Column(db.String(100))
    item_price = db.Column(db.Float, default=0.0)
    item_qty = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# جدول المخزن
class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, default=0.0)

with app.app_context():
    db.create_all()

# واجهة التطبيق عبر Streamlit
st.title("🏭 معمل الرافدين لصناعة وتصليح المبردات")

# القائمة الجانبية للتنقل بين الأقسام من الموبايل
menu = st.sidebar.selectbox("القائمة الرئيسية", ["تسجيل عملية جديدة", "أرشيف العمليات والبحث", "إدارة المخزن"])

if menu == "تسجيل عملية جديدة":
    st.header("تسجيل عملية صيانة أو بيع جديدة")
    
    with st.form("trans_form"):
        client_name = st.text_input("اسم العميل", "عميل عام")
        maint_desc = st.text_input("وصف الصيانة / العمل")
        maint_price = st.number_input("أجور الصيانة (د.ع)", min_value=0.0, value=0.0)
        item_name = st.text_input("اسم المادة / القطعة المباعة")
        item_price = st.number_input("سعر القطعة (د.ع)", min_value=0.0, value=0.0)
        item_qty = st.number_input("الكمية", min_value=1, value=1)
        
        submitted = st.form_submit_button("حفظ العملية")
        if submitted:
            with app.app_context():
                new_trans = Transaction(
                    client_name=client_name,
                    maint_desc=maint_desc,
                    maint_price=maint_price,
                    item_name=item_name,
                    item_price=item_price,
                    item_qty=int(item_qty)
                )
                db.session.add(new_trans)
                db.session.commit()
            st.success("تم حفظ العملية بنجاح!")

    st.subheader("آخر العمليات المسجلة")
    with app.app_context():
        transactions = Transaction.query.order_by(Transaction.created_at.desc()).limit(5).all()
        for t in transactions:
            total = (t.maint_price or 0) + ((t.item_price or 0) * (t.item_qty or 1))
            st.info(f"**العميل:** {t.client_name} | **التفاصيل:** {t.maint_desc} - {t.item_name} | **المجموع:** {total} د.ع")

elif menu == "أرشيف العمليات والبحث":
    st.header("أرشيف العمليات والبحث")
    search_query = st.text_input("ابحث باسم العميل أو تفاصيل الصيانة...")
    
    with app.app_context():
        if search_query:
            results = Transaction.query.filter(
                (Transaction.client_name.contains(search_query)) | 
                (Transaction.maint_desc.contains(search_query))
            ).order_by(Transaction.created_at.desc()).all()
        else:
            results = Transaction.query.order_by(Transaction.created_at.desc()).all()
            
        for t in results:
            total = (t.maint_price or 0) + ((t.item_price or 0) * (t.item_qty or 1))
            st.write(f"📌 **رقم العمل:** #{t.id} | **التاريخ:** {t.created_at.strftime('%Y-%m-%d')} | **العميل:** {t.client_name} | **المجموع:** {total} د.ع")

elif menu == "إدارة المخزن":
    st.header("إدارة المخزن والمواد الخام")
    
    with st.form("inv_form"):
        inv_name = st.text_input("اسم المادة / القطعة")
        inv_qty = st.number_input("الكمية المضافة", min_value=0, value=1)
        inv_price = st.number_input("السعر المفرد (د.ع)", min_value=0.0, value=0.0)
        
        inv_submitted = st.form_submit_button("إضافة / تحديث المخزن")
        if inv_submitted and inv_name:
            with app.app_context():
                existing = Inventory.query.filter_by(name=inv_name).first()
                if existing:
                    existing.quantity += int(inv_qty)
                    existing.price = inv_price
                else:
                    new_item = Inventory(name=inv_name, quantity=int(inv_qty), price=inv_price)
                    db.session.add(new_item)
                db.session.commit()
            st.success("تم تحديث المخزن بنجاح!")
            
    st.subheader("محتويات المخزن الحالي")
    with app.app_context():
        items = Inventory.query.all()
        for item in items:
            st.write(f"📦 **المادة:** {item.name} | **الكمية المتاحة:** {item.quantity} | **السعر:** {item.price} د.ع")
