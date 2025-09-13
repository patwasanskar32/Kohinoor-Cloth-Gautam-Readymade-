import streamlit as st
import pandas as pd
import pytz
from datetime import datetime, time
import json
import hashlib
import os

# --- CONFIGURATION ---
ATTENDANCE_FILE = 'attendance.csv'
USERS_FILE = 'users.json'
INDIA_TIMEZONE = pytz.timezone('Asia/Kolkata')
PASSWORD_SALT = "a_unique_salt_for_your_app"

# --- UTILITY FUNCTIONS ---
def hash_password(password: str) -> str:
    return hashlib.sha256(str.encode(password + PASSWORD_SALT)).hexdigest()

def load_data():
    """Load users and attendance, ensure owner exists."""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE,'r') as f:
                users = json.load(f)
        except:
            users = {}
    else:
        users = {}

    if 'owner' not in users:
        users['owner'] = {'password': hash_password('owner_password'),'role':'owner'}
        save_user_data(users)

    if os.path.exists(ATTENDANCE_FILE):
        try:
            attendance_df = pd.read_csv(ATTENDANCE_FILE, parse_dates=['date'], dayfirst=False)
        except:
            attendance_df = pd.DataFrame(columns=['username','date','check_in_time','check_out_time','is_present'])
    else:
        attendance_df = pd.DataFrame(columns=['username','date','check_in_time','check_out_time','is_present'])
        save_attendance_data(attendance_df)

    # Ensure all required columns exist
    for col in ['check_out_time','check_in_time','is_present']:
        if col not in attendance_df.columns:
            attendance_df[col] = ""

    attendance_df['date'] = pd.to_datetime(attendance_df['date'], errors='coerce')

    return users, attendance_df

def save_user_data(users: dict):
    with open(USERS_FILE,'w') as f:
        json.dump(users,f,indent=4)

def save_attendance_data(df: pd.DataFrame):
    df_copy = df.copy()
    if 'date' in df_copy.columns:
        df_copy['date'] = pd.to_datetime(df_copy['date'], errors='coerce').dt.strftime('%Y-%m-%d')

    def _format_time(v):
        if pd.isna(v) or v=="":
            return ""
        try:
            parsed = pd.to_datetime(v, errors='coerce')
            if pd.isna(parsed):
                return str(v)
            return parsed.strftime('%H:%M:%S')
        except:
            return str(v)

    for col in ['check_in_time','check_out_time']:
        if col in df_copy.columns:
            df_copy[col] = df_copy[col].apply(_format_time)

    df_copy.to_csv(ATTENDANCE_FILE,index=False)

# --- INITIALIZATION ---
users, attendance_df = load_data()

# Session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'role' not in st.session_state:
    st.session_state.role = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# --- LOGIN PAGE ---
def show_login_page():
    st.title("Attendance Web App")
    st.subheader("Login to your account")
    with st.form(key='login_form'):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_button = st.form_submit_button("Login")
    if login_button:
        if username and username in users and users[username]['password']==hash_password(password):
            st.session_state.authenticated=True
            st.session_state.username=username
            st.session_state.role=users[username]['role']
            st.session_state.page='owner_dashboard' if st.session_state.role=='owner' else 'staff_dashboard'
            st.rerun()
        else:
            st.error("Invalid username or password")

# --- OWNER DASHBOARD ---
def show_owner_dashboard():
    st.title(f"Welcome, {st.session_state.username.capitalize()} (Owner)")
    st.markdown("---")

    col1,col2,col3,col4 = st.columns([1,1,1,1])
    with col1:
        if st.button("Add New Staff", use_container_width=True):
            st.session_state.page='add_staff'
            st.rerun()
    with col2:
        if st.button("Mark Attendance", use_container_width=True):
            st.session_state.page='mark_attendance'
            st.rerun()
    with col3:
        if st.button("Remove Staff", use_container_width=True):
            st.session_state.page='remove_staff'
            st.rerun()
    with col4:
        if st.button("Warnings", use_container_width=True):
            st.session_state.page='warnings'
            st.rerun()

    st.markdown("---")
    st.subheader("Full Attendance Sheet")
    if not attendance_df.empty:
        display_df = attendance_df.copy()
        display_df['date'] = pd.to_datetime(display_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')

        # Ensure check_in/out columns exist
        for col in ['check_in_time','check_out_time']:
            if col not in display_df.columns:
                display_df[col] = ""
        
        # Format times safely
        display_df['check_in_time'] = pd.to_datetime(display_df['check_in_time'], errors='coerce').dt.strftime('%I:%M %p').fillna('')
        display_df['check_out_time'] = pd.to_datetime(display_df['check_out_time'], errors='coerce').dt.strftime('%I:%M %p').fillna('')
        display_df['status'] = display_df['is_present'].apply(lambda x:'Present' if str(x).lower() in ('true','1','yes') or x is True else 'Absent')
        st.dataframe(display_df[['username','date','check_in_time','check_out_time','status']].sort_values(by='date',ascending=False), use_container_width=True)
    else:
        st.info("No attendance records found.")

# --- STAFF DASHBOARD ---
def show_staff_dashboard():
    st.title(f"Welcome, {st.session_state.username.capitalize()} (Staff)")
    st.markdown("---")
    st.subheader("Your Attendance History")
    staff_attendance = attendance_df[attendance_df['username']==st.session_state.username]
    if not staff_attendance.empty:
        display_df = staff_attendance.copy()
        display_df['date'] = pd.to_datetime(display_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')

        for col in ['check_in_time','check_out_time']:
            if col not in display_df.columns:
                display_df[col] = ""
        display_df['check_in_time'] = pd.to_datetime(display_df['check_in_time'], errors='coerce').dt.strftime('%I:%M %p').fillna('')
        display_df['check_out_time'] = pd.to_datetime(display_df['check_out_time'], errors='coerce').dt.strftime('%I:%M %p').fillna('')
        display_df['status'] = display_df['is_present'].apply(lambda x:'Present' if str(x).lower() in ('true','1','yes') or x is True else 'Absent')
        st.dataframe(display_df[['date','check_in_time','check_out_time','status']].sort_values(by='date',ascending=False), use_container_width=True)
    else:
        st.info("No attendance records found for you.")

# --- ADD STAFF ---
def show_add_staff_page():
    st.title("Add New Staff Member")
    if st.button("Back to Dashboard"):
        st.session_state.page='owner_dashboard'
        st.rerun()
    st.markdown("---")
    with st.form(key='add_staff_form'):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Add Staff")
    if submit_button:
        if not new_username or not new_password:
            st.error("Please provide both username and password.")
        elif new_username in users:
            st.error("Username already exists!")
        else:
            users[new_username]={'password':hash_password(new_password),'role':'staff'}
            save_user_data(users)
            st.success(f"Staff member '{new_username}' added successfully!")
            st.session_state.page='owner_dashboard'
            st.rerun()

# --- REMOVE STAFF ---
def show_remove_staff_page():
    st.title("Remove Staff Member")
    if st.button("Back to Dashboard"):
        st.session_state.page='owner_dashboard'
        st.rerun()
    staff_members = [u for u,d in users.items() if d.get('role')=='staff']
    if not staff_members:
        st.info("No staff members to remove.")
        return
    selected_staff = st.selectbox("Select Staff", staff_members)
    if st.button("Remove Staff"):
        del users[selected_staff]
        save_user_data(users)
        st.success(f"Staff member '{selected_staff}' removed.")
        st.session_state.page='owner_dashboard'
        st.rerun()

# --- WARNING PAGE ---
def show_warning_page():
    st.title("Issue Warning to Staff")
    if st.button("Back to Dashboard"):
        st.session_state.page='owner_dashboard'
        st.rerun()
    staff_members=[u for u,d in users.items() if d.get('role')=='staff']
    if not staff_members:
        st.info("No staff found.")
        return
    selected_staff=st.selectbox("Select Staff", staff_members)
    warning_text=st.text_area("Enter Warning Message")
    if st.button("Send Warning"):
        if selected_staff and warning_text:
            st.success(f"Warning for '{selected_staff}': {warning_text}")
        else:
            st.error("Please enter warning text.")

# --- MARK/EDIT ATTENDANCE ---
def show_mark_attendance_page():
    global attendance_df
    st.title("Mark/Edit Attendance")
    if st.button("Back to Dashboard"):
        st.session_state.page='owner_dashboard'
        st.rerun()
    staff_members=[u for u,d in users.items() if d.get('role')=='staff']
    if not staff_members:
        st.warning("No staff members to mark attendance.")
        return
    with st.form(key='mark_attendance_form'):
        selected_staff=st.selectbox("Select Staff", staff_members)
        selected_date=st.date_input("Select Date", value=datetime.now(INDIA_TIMEZONE).date())
        check_in_time=st.time_input("Check-in Time", value=datetime.now(INDIA_TIMEZONE).time())
        check_out_time=st.time_input("Check-out Time", value=datetime.now(INDIA_TIMEZONE).time())
        is_present=st.checkbox("Present", value=True)
        submit_button=st.form_submit_button("Submit Attendance")
    if submit_button:
        selected_date_dt=pd.to_datetime(selected_date)
        check_in_str=check_in_time.strftime("%H:%M:%S")
        check_out_str=check_out_time.strftime("%H:%M:%S")
        mask_user=attendance_df['username']==selected_staff
        mask_date=attendance_df['date'].dt.date==selected_date
        existing_index=attendance_df[mask_user & mask_date].index
        if existing_index.any():
            idx=existing_index[0]
            attendance_df.at[idx,'check_in_time']=check_in_str
            attendance_df.at[idx,'check_out_time']=check_out_str
            attendance_df.at[idx,'is_present']=is_present
            st.success(f"Attendance updated for '{selected_staff}' on {selected_date}")
        else:
            new_record=pd.DataFrame([{
                'username':selected_staff,
                'date':selected_date_dt,
                'check_in_time':check_in_str,
                'check_out_time':check_out_str,
                'is_present':is_present
            }])
            attendance_df=pd.concat([attendance_df,new_record],ignore_index=True)
            st.success(f"Attendance marked for '{selected_staff}' on {selected_date}")
        save_attendance_data(attendance_df)
        st.session_state.page='owner_dashboard'
        st.rerun()

# --- LOGOUT ---
def perform_logout():
    st.session_state.authenticated=False
    st.session_state.username=None
    st.session_state.role=None
    st.session_state.page='login'
    st.rerun()

def show_logout_button():
    if st.sidebar.button("Logout"):
        perform_logout()

# --- NAVIGATION ---
if not st.session_state.authenticated:
    show_login_page()
else:
    st.sidebar.title("Navigation")
    if st.session_state.role=='owner':
        if st.sidebar.button("Dashboard"): st.session_state.page='owner_dashboard'; st.rerun()
        if st.sidebar.button("Add Staff"): st.session_state.page='add_staff'; st.rerun()
        if st.sidebar.button("Mark Attendance"): st.session_state.page='mark_attendance'; st.rerun()
        if st.sidebar.button("Remove Staff"): st.session_state.page='remove_staff'; st.rerun()
        if st.sidebar.button("Warnings"): st.session_state.page='warnings'; st.rerun()
    else:
        if st.sidebar.button("My Attendance"): st.session_state.page='staff_dashboard'; st.rerun()
    st.sidebar.markdown("---")
    show_logout_button()

    # Render page
    if st.session_state.page=='owner_dashboard' and st.session_state.role=='owner': show_owner_dashboard()
    elif st.session_state.page=='staff_dashboard' and st.session_state.role=='staff': show_staff_dashboard()
    elif st.session_state.page=='add_staff' and st.session_state.role=='owner': show_add_staff_page()
    elif st.session_state.page=='remove_staff' and st.session_state.role=='owner': show_remove_staff_page()
    elif st.session_state.page=='warnings' and st.session_state.role=='owner': show_warning_page()
    elif st.session_state.page=='mark_attendance' and st.session_state.role=='owner': show_mark_attendance_page()
    else: st.error("Access Denied.")
