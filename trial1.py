import streamlit as st
import pandas as pd
import pytz
from datetime import datetime
import json
import hashlib

# --- CONFIGURATION ---
ATTENDANCE_FILE = 'attendance.csv'
USERS_FILE = 'users.json'
INDIA_TIMEZONE = pytz.timezone('Asia/Kolkata')
PASSWORD_SALT = "a_unique_salt_for_your_app"

# --- UTILITY FUNCTIONS ---
def hash_password(password):
    """Hashes a password with a salt for security."""
    return hashlib.sha256(str.encode(password + PASSWORD_SALT)).hexdigest()

def load_data():
    """Loads user and attendance data, initializing if files don't exist."""
    # Initialize users.json
    try:
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        users = {
            'owner': {'password': hash_password('owner_password'), 'role': 'owner'}
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)
    
    # Initialize attendance.csv
    try:
        attendance_df = pd.read_csv(ATTENDANCE_FILE, parse_dates=['date'])
    except FileNotFoundError:
        attendance_df = pd.DataFrame(columns=['username', 'date', 'check_in_time', 'is_present'])
        attendance_df.to_csv(ATTENDANCE_FILE, index=False)
    
    return users, attendance_df

def save_user_data(users):
    """Saves user data back to the JSON file."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def save_attendance_data(df):
    """Saves attendance data back to the CSV file."""
    df.to_csv(ATTENDANCE_FILE, index=False)

# --- INITIALIZATION ---
users, attendance_df = load_data()

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'role' not in st.session_state:
    st.session_state.role = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# --- MAIN APP LOGIC ---

def show_login_page():
    st.title("Attendance Web App")
    st.subheader("Login to your account")
    
    with st.form(key='login_form'):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_button = st.form_submit_button("Login")
        
    if login_button:
        if username in users and users[username]['password'] == hash_password(password):
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.role = users[username]['role']
            if st.session_state.role == 'owner':
                st.session_state.page = 'owner_dashboard'
            else:
                st.session_state.page = 'staff_dashboard'
            st.rerun()
        else:
            st.error("Invalid username or password")

def show_owner_dashboard():
    st.title(f"Welcome, {st.session_state.username.capitalize()} (Owner)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.button("Add New Staff", on_click=lambda: st.session_state.update(page='add_staff'), use_container_width=True)
    with col2:
        st.button("Mark Attendance", on_click=lambda: st.session_state.update(page='mark_attendance'), use_container_width=True)
    
    st.markdown("---")

    st.subheader("Full Attendance Sheet")
    if not attendance_df.empty:
        display_df = attendance_df.copy()
        display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%Y-%m-%d')
        display_df['check_in_time'] = pd.to_datetime(display_df['check_in_time']).dt.strftime('%I:%M %p')
        display_df['status'] = display_df['is_present'].apply(lambda x: 'Present' if x else 'Absent')
        
        st.dataframe(display_df[['username', 'date', 'check_in_time', 'status']].sort_values(by='date', ascending=False), use_container_width=True)
    else:
        st.info("No attendance records found.")

def show_staff_dashboard():
    st.title(f"Welcome, {st.session_state.username.capitalize()} (Staff)")
    st.markdown("---")
    
    st.subheader("Your Attendance History")
    staff_attendance = attendance_df[attendance_df['username'] == st.session_state.username]
    
    if not staff_attendance.empty:
        display_df = staff_attendance.copy()
        display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%Y-%m-%d')
        display_df['check_in_time'] = pd.to_datetime(display_df['check_in_time']).dt.strftime('%I:%M %p')
        display_df['status'] = display_df['is_present'].apply(lambda x: 'Present' if x else 'Absent')
        
        st.dataframe(display_df[['date', 'check_in_time', 'status']].sort_values(by='date', ascending=False), use_container_width=True)
    else:
        st.info("No attendance records found for you.")

def show_add_staff_page():
    st.title("Add New Staff Member")
    st.button("Back to Dashboard", on_click=lambda: st.session_state.update(page='owner_dashboard'))
    st.markdown("---")
    
    with st.form(key='add_staff_form'):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Add Staff")
        
    if submit_button:
        if new_username in users:
            st.error("Username already exists!")
        else:
            users[new_username] = {'password': hash_password(new_password), 'role': 'staff'}
            save_user_data(users)
            st.success(f"Staff member '{new_username}' added successfully!")
            st.info("You can now mark their attendance.")
            st.session_state.page = 'owner_dashboard'
            st.rerun()

def show_mark_attendance_page():
    global attendance_df

    st.title("Mark Attendance")
    st.button("Back to Dashboard", on_click=lambda: st.session_state.update(page='owner_dashboard'))
    st.markdown("---")
    
    staff_members = [user for user, data in users.items() if data['role'] == 'staff']
    
    if not staff_members:
        st.warning("No staff members to mark attendance for. Please add staff first.")
    else:
        with st.form(key='mark_attendance_form'):
            selected_staff = st.selectbox("Select Staff Member", staff_members)
            col1, col2 = st.columns(2)
            with col1:
                mark_present_button = st.form_submit_button("Mark Present", type="primary")
            with col2:
                mark_absent_button = st.form_submit_button("Mark Absent", type="secondary")
            
        if mark_present_button or mark_absent_button:
            
            # --- FIX FOR THE ATTRIBUTE ERROR ---
            attendance_df['date'] = pd.to_datetime(attendance_df['date'])
            # ------------------------------------

            now_ist = datetime.now(INDIA_TIMEZONE)
            current_date = now_ist.date()
            current_time = now_ist.time()
            
            if ((attendance_df['username'] == selected_staff) & (attendance_df['date'].dt.date == current_date)).any():
                st.warning(f"Attendance for '{selected_staff}' has already been marked for today.")
            else:
                is_present = bool(mark_present_button)
                new_record = pd.DataFrame([{
                    'username': selected_staff,
                    'date': current_date,
                    'check_in_time': current_time if is_present else None,
                    'is_present': is_present
                }])
                
                attendance_df = pd.concat([attendance_df, new_record], ignore_index=True)
                save_attendance_data(attendance_df)
                
                if is_present:
                    st.success(f"Attendance for '{selected_staff}' marked as Present!")
                else:
                    st.success(f"Attendance for '{selected_staff}' marked as Absent!")
                
                st.session_state.page = 'owner_dashboard'
                st.rerun()

def show_logout_button():
    st.sidebar.button("Logout", on_click=lambda: st.session_state.update(authenticated=False, username=None, role=None, page='login'))

# --- NAVIGATION ---
if not st.session_state.authenticated:
    show_login_page()
else:
    st.sidebar.title("Navigation")
    if st.session_state.role == 'owner':
        st.sidebar.button("Dashboard", on_click=lambda: st.session_state.update(page='owner_dashboard'), use_container_width=True)
        st.sidebar.button("Add Staff", on_click=lambda: st.session_state.update(page='add_staff'), use_container_width=True)
        st.sidebar.button("Mark Attendance", on_click=lambda: st.session_state.update(page='mark_attendance'), use_container_width=True)
    else:
        st.sidebar.button("My Attendance", on_click=lambda: st.session_state.update(page='staff_dashboard'), use_container_width=True)
    
    st.sidebar.markdown("---")
    show_logout_button()
    
    if st.session_state.page == 'owner_dashboard' and st.session_state.role == 'owner':
        show_owner_dashboard()
    elif st.session_state.page == 'staff_dashboard' and st.session_state.role == 'staff':
        show_staff_dashboard()
    elif st.session_state.page == 'add_staff' and st.session_state.role == 'owner':
        show_add_staff_page()
    elif st.session_state.page == 'mark_attendance' and st.session_state.role == 'owner':
        show_mark_attendance_page()
    else:
        st.error("Access Denied.")