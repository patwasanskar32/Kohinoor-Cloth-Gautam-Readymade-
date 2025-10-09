import streamlit as st
import pandas as pd
import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import pytz
import qrcode
from pyzbar.pyzbar import decode
import numpy as np
import json

# ---------------- CONFIG ----------------
USERS_FILE = "users.csv"
ATTENDANCE_FILE = "attendance.csv"
WARNINGS_FILE = "warnings.csv"
PHOTOS_DIR = "photos"
QR_DIR = "qrcodes"
SHOP_INFO_FILE = "shop_info.json"

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)

# ---------------- SESSION STATE ----------------
if "page" not in st.session_state: st.session_state.page = "login"
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "role" not in st.session_state: st.session_state.role = ""

# ---------------- HELPER FUNCTIONS ----------------
def load_users():
    if os.path.exists(USERS_FILE):
        return pd.read_csv(USERS_FILE)
    return pd.DataFrame(columns=["username","password","role","photo_path","qr_path"])

def save_users(df): df.to_csv(USERS_FILE,index=False)

def load_attendance():
    if os.path.exists(ATTENDANCE_FILE):
        return pd.read_csv(ATTENDANCE_FILE)
    return pd.DataFrame(columns=["username","check_in_time","check_out_time"])

def save_attendance(df): df.to_csv(ATTENDANCE_FILE,index=False)

def load_warnings():
    if os.path.exists(WARNINGS_FILE):
        return pd.read_csv(WARNINGS_FILE)
    return pd.DataFrame(columns=["username","warning","date_time"])

def save_warnings(df): df.to_csv(WARNINGS_FILE,index=False)

def load_shop_info():
    if os.path.exists(SHOP_INFO_FILE):
        with open(SHOP_INFO_FILE,"r") as f: return json.load(f)
    return {"shop_name":"My Shop","shop_logo_path":""}

def save_shop_info(shop_name,shop_logo_path):
    with open(SHOP_INFO_FILE,"w") as f:
        json.dump({"shop_name":shop_name,"shop_logo_path":shop_logo_path},f)

def ensure_default_owner():
    users = load_users()
    if "owner" not in users["username"].values:
        default_owner = pd.DataFrame([{
            "username":"owner","password":"owner123",
            "role":"owner","photo_path":"","qr_path":""
        }])
        users = pd.concat([users,default_owner],ignore_index=True)
        save_users(users)
        generate_qr_code("owner")

def generate_qr_code(username):
    qr_path = os.path.join(QR_DIR,f"{username}.png")
    if not os.path.exists(qr_path):
        img = qrcode.make(username)
        img.save(qr_path)
    return qr_path

def mark_attendance(username):
    df = load_attendance()
    india_time = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india_time)
    user_records = df[df["username"]==username]
    if user_records.empty or pd.notna(user_records.iloc[-1]["check_out_time"]):
        df = pd.concat([df,pd.DataFrame([{
            "username":username,
            "check_in_time":now.strftime("%Y-%m-%d %H:%M:%S"),
            "check_out_time":""
        }])],ignore_index=True)
        save_attendance(df)
        st.success(f"{username} checked in at {now.strftime('%I:%M %p')}")
    else:
        df.loc[df["username"]==username,"check_out_time"]=now.strftime("%Y-%m-%d %H:%M:%S")
        save_attendance(df)
        st.info(f"{username} checked out at {now.strftime('%I:%M %p')}")

def scan_qr_image(uploaded_file):
    img = Image.open(uploaded_file)
    decoded_objects = decode(img)
    if decoded_objects:
        return decoded_objects[0].data.decode("utf-8")
    return None

def scan_qr_camera(label="Scan QR"):
    qr_image = st.camera_input(label)
    if qr_image:
        img = Image.open(qr_image).convert("RGB")
        decoded_objects = decode(np.array(img))
        if decoded_objects:
            return decoded_objects[0].data.decode("utf-8")
    return None

# ---------------- LOGIN ----------------
def login_page():
    st.title("🔐 Smart Attendance System")
    st.subheader("Login with Username/Password")
    username = st.text_input("Username")
    password = st.text_input("Password",type="password")
    if st.button("Login"):
        users = load_users()
        if username in users["username"].values:
            user = users[users["username"]==username].iloc[0]
            if user["password"]==password:
                st.session_state.logged_in=True
                st.session_state.username=username
                st.session_state.role=user["role"]
                st.session_state.page="dashboard"
        else: st.error("Invalid credentials")
    st.markdown("---")
    st.subheader("Or Login with QR Code")
    if st.button("Go to QR Login Page"):
        st.session_state.page="qr_login"

def qr_login_page():
    st.title("🔑 Login via QR Code")
    st.write("Upload QR image or scan via camera")
    qr_file = st.file_uploader("Upload QR Code",type=["png","jpg"])
    qr_camera_button = st.button("Scan QR via Camera")
    username=None
    if qr_file: username = scan_qr_image(qr_file)
    elif qr_camera_button: username = scan_qr_camera("Scan QR to login")
    if username:
        users = load_users()
        if username in users["username"].values:
            user = users[users["username"]==username].iloc[0]
            st.session_state.logged_in=True
            st.session_state.username=username
            st.session_state.role=user["role"]
            st.session_state.page="dashboard"
        else: st.error("QR does not match any user")
    if st.button("Back to Login Page"):
        st.session_state.page="login"

# ---------------- DASHBOARD ----------------
def dashboard():
    role = st.session_state.role
    username = st.session_state.username
    st.sidebar.title(f"Welcome, {username}")
    if st.sidebar.button("Logout"): logout()
    
    shop_info = load_shop_info()
    
    if role=="owner":
        st.subheader("Owner Dashboard")
        menu = st.sidebar.radio("Select Feature:",["Mark Attendance","Edit/Delete Attendance","Add Staff","Remove Staff","Warnings","Shop Info","Owner ID Card"])
        
        if menu=="Mark Attendance":
            st.write("📷 Mark Attendance via QR")
            qr_file = st.file_uploader("Upload QR",type=["png","jpg"],key="owner_att")
            if qr_file:
                uname = scan_qr_image(qr_file)
                if uname: mark_attendance(uname)
            if st.button("Scan QR via Camera"):
                uname = scan_qr_camera("Owner Scan QR")
                if uname: mark_attendance(uname)
        
        elif menu=="Edit/Delete Attendance":
            att_df = load_attendance()
            if not att_df.empty:
                att_df["check_in_time"]=pd.to_datetime(att_df["check_in_time"])
                att_df["check_out_time"]=pd.to_datetime(att_df["check_out_time"])
                for i,row in att_df.iterrows():
                    cols = st.columns([2,2,2,1,1])
                    cols[0].write(row["username"])
                    ci = cols[1].date_input("Check-in",value=row["check_in_time"].date() if pd.notna(row["check_in_time"]) else datetime.today(),key=f"ci{i}")
                    co = cols[2].date_input("Check-out",value=row["check_out_time"].date() if pd.notna(row["check_out_time"]) else datetime.today(),key=f"co{i}")
                    if cols[3].button("Update",key=f"up{i}"):
                        att_df.at[i,"check_in_time"]=datetime.combine(ci,row["check_in_time"].time() if pd.notna(row["check_in_time"]) else datetime.min.time())
                        att_df.at[i,"check_out_time"]=datetime.combine(co,row["check_out_time"].time() if pd.notna(row["check_out_time"]) else datetime.min.time())
                        save_attendance(att_df)
                        st.success("Updated!")
                    if cols[4].button("Delete",key=f"del{i}"):
                        att_df = att_df.drop(i)
                        save_attendance(att_df)
                        st.success("Deleted!")
                st.dataframe(att_df)
            else: st.info("No attendance records yet.")
        
        elif menu=="Add Staff":
            st.write("➕ Add New Staff")
            uname = st.text_input("Username",key="add_user")
            pwd = st.text_input("Password",type="password",key="add_pwd")
            photo = st.file_uploader("Photo",type=["png","jpg"],key="add_photo")
            if st.button("Add Staff"):
                if uname and pwd:
                    users = load_users()
                    if uname in users["username"].values: st.warning("Username exists!")
                    else:
                        photo_path=""
                        if photo: 
                            photo_path = os.path.join(PHOTOS_DIR,f"{uname}.png")
                            with open(photo_path,"wb") as f: f.write(photo.read())
                        qr_path = generate_qr_code(uname)
                        new_user = pd.DataFrame([{"username":uname,"password":pwd,"role":"staff","photo_path":photo_path,"qr_path":qr_path}])
                        users=pd.concat([users,new_user],ignore_index=True)
                        save_users(users)
                        st.success(f"Staff '{uname}' added!")
        
        elif menu=="Remove Staff":
            users = load_users()
            staff_list = users[users["role"]=="staff"]["username"].tolist()
            if staff_list:
                remove = st.selectbox("Select Staff to Remove",staff_list)
                if st.button("Remove"):
                    users = users[users["username"]!=remove]
                    save_users(users)
                    st.success(f"Staff '{remove}' removed!")
            else: st.info("No staff found.")
        
        elif menu=="Warnings":
            users = load_users()
            staff_list = users[users["role"]=="staff"]["username"].tolist()
            if staff_list:
                staff_warn = st.selectbox("Select Staff",staff_list)
                text = st.text_input("Warning")
                if st.button("Give Warning"):
                    if text:
                        df = load_warnings()
                        new = pd.DataFrame([{"username":staff_warn,"warning":text,"date_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                        df=pd.concat([df,new],ignore_index=True)
                        save_warnings(df)
                        st.success("Warning sent")
        
        elif menu=="Shop Info":
            name = st.text_input("Shop Name",value=shop_info["shop_name"])
            logo = st.file_uploader("Shop Logo",type=["png","jpg"])
            if st.button("Save Shop Info"):
                logo_path = shop_info.get("shop_logo_path","")
                if logo:
                    logo_path=os.path.join(PHOTOS_DIR,"shop_logo.png")
                    with open(logo_path,"wb") as f: f.write(logo.read())
                save_shop_info(name,logo_path)
                st.success("Shop Info Saved")
        
        elif menu=="Owner ID Card":
            st.write("Owner ID Card")
            shop_info = load_shop_info()
            qr_path = generate_qr_code("owner")
            id_card = Image.new("RGB",(400,200),"white")
            draw = ImageDraw.Draw(id_card)
            font = ImageFont.load_default()
            # Shop logo
            if shop_info.get("shop_logo_path") and os.path.exists(shop_info["shop_logo_path"]):
                logo_img = Image.open(shop_info["shop_logo_path"]).resize((50,50))
                id_card.paste(logo_img,(10,10))
            draw.text((70,10),shop_info.get("shop_name","My Shop"),fill="black",font=font)
            draw.text((10,70),"Owner: owner",fill="black",font=font)
            if os.path.exists(qr_path):
                qr_img = Image.open(qr_path).resize((80,80))
                id_card.paste(qr_img,(300,100))
            st.image(id_card)

    else: # Staff
        st.subheader("Staff Dashboard")
        menu = st.sidebar.radio("Select Feature:",["View QR","Attendance History","Warnings","Staff ID Card"])
        if menu=="View QR":
            users = load_users()
            data = users[users["username"]==username].iloc[0]
            qr_path = data["qr_path"]
            if os.path.exists(qr_path):
                st.image(qr_path,caption="Your QR Code",width=200)
        elif menu=="Attendance History":
            df = load_attendance()
            records = df[df["username"]==username]
            if not records.empty:
                records["check_in_time"]=pd.to_datetime(records["check_in_time"]).dt.strftime("%d-%b %I:%M %p")
                records["check_out_time"]=pd.to_datetime(records["check_out_time"],errors="coerce").apply(lambda x:x.strftime("%d-%b %I:%M %p") if pd.notna(x) else "")
                st.dataframe(records)
            else: st.info("No records yet.")
        elif menu=="Warnings":
            df = load_warnings()
            warnings = df[df["username"]==username]
            if not warnings.empty:
                warnings["date_time"]=pd.to_datetime(warnings["date_time"]).dt.strftime("%d-%b %I:%M %p")
                st.dataframe(warnings[["warning","date_time"]])
            else: st.info("No warnings")
        elif menu=="Staff ID Card":
            users = load_users()
            data = users[users["username"]==username].iloc[0]
            qr_path = data["qr_path"]
            photo_path = data["photo_path"]
            shop_info = load_shop_info()
            id_card = Image.new("RGB",(400,200),"white")
            draw = ImageDraw.Draw(id_card)
            font = ImageFont.load_default()
            # Shop logo
            if shop_info.get("shop_logo_path") and os.path.exists(shop_info["shop_logo_path"]):
                logo_img = Image.open(shop_info["shop_logo_path"]).resize((50,50))
                id_card.paste(logo_img,(10,10))
            draw.text((70,10),shop_info.get("shop_name","My Shop"),fill="black",font=font)
            # Staff photo
            if photo_path and os.path.exists(photo_path):
                ph_img = Image.open(photo_path).resize((80,80))
                id_card.paste(ph_img,(10,70))
            draw.text((100,80),f"Name: {username}",fill="black",font=font)
            if qr_path and os.path.exists(qr_path):
                qr_img = Image.open(qr_path).resize((80,80))
                id_card.paste(qr_img,(300,100))
            st.image(id_card)

def logout():
    st.session_state.logged_in=False
    st.session_state.username=""
    st.session_state.role=""
    st.session_state.page="login"

# ---------------- MAIN ----------------
def main():
    ensure_default_owner()
    if not st.session_state.logged_in:
        if st.session_state.page=="login":
            login_page()
        elif st.session_state.page=="qr_login":
            qr_login_page()
    else:
        dashboard()

if __name__=="__main__":
    main()
