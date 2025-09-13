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
    """Hashes a password with a salt for security."""
    return hashlib.sha256(str.encode(password + PASSWORD_SALT)).hexdigest()

def load_data():
    """Loads user and attendance data, initializing if files don't exist."""
    # Load or initialize users.json
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
        except (json.JSONDecodeError, IOError):
            users = {}
    else:
        users = {}

    # Ensure an owner account exists (only created if missing)
    if 'owner' not in users:
        users['owner'] = {'password': hash_password('owner_password'), 'role': 'owner'}
        save_user_data(users)

    # Load or initialize attendance.csv
    if os.path.exists(ATTENDANCE_FILE):
        try:
            attendance_df = pd.read_csv(ATTENDANCE_FILE, parse_dates=['date'], dayfirst=False)
        except (ValueError, IOError):
            attendance_df = pd.DataFrame(columns=['username', 'date', 'check_in_time', 'is_present'])
    else:
        attendance_df = pd.DataFrame(columns=['username', 'date', 'check_in_time', 'is_present'])
        save_attendance_data(attendance_df)

    # Ensure date column is datetime (coerce invalid)
    if 'date' in attendance_df.columns:
        attendance_df['date'] = pd.to_datetime(attendance_df['date'], errors='coerce')
    else:
        attendance_df['date'] = pd.to_datetime(pd.Series([], dtype='datetime64[ns]'))

    return users, attendance_df

def save_user_data(users: dict):
    """Saves user data back to the JSON file."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def save_attendance_data(df: pd.DataFrame):
    """Saves attendance data back to the CSV file with consistent formatting."""
    df_copy = df.copy()

    # Ensure 'date' is formatted as YYYY-MM-DD
    if 'date' in df_copy.columns:
        df_copy['date'] = pd.to_datetime(df_copy['date'], errors='coerce').dt.strftime('%Y-%m-%d')

    # Format check_in_time
    if 'check_in_time' in df_copy.columns:
        def _format_time(v):
            if pd.isna(v):
                return ""
            try:
                parsed = pd.to_datetime(v, errors='coerce')
                if pd.isna(parsed):
                    return str(v)
                return parsed.strftime('%H:%M:%S')
            except Exception:
                return str(v)

        df_copy['check_in_time'] = df_copy['check_in_time'].apply(_format_time)

    df_copy.to_csv(ATTENDANCE_FILE, index=False)

# --- INITIALIZATION ---
users, attendance_df = load_data()

# Initialize session state safely
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
        if username and username in users and users[username]['password'] == hash_password(password):
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.role = users[username]['role']
            st.session_state.page = 'owner_dashboard' if st.session_state.role == 'owner' else 'staff_dashboard'
            st.rerun()
        else:
            st.error("Invalid username or password")

def show_owner_dashboard():
    st.title(f"Welcome, {st.session_state.username.capitalize()} (Owner)")
    st.markdown("---")

    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("Add New Staff", use_container_width=True):
            st.session_state.page = 'add_staff'
            st.rerun()
    with col2:
        if st.button("Mark Attendance", use_container_width=True):
            st.session_state.page = 'mark_attendance'
            st.rerun()

    st.markdown("---")

    st.subheader("Full Attendance Sheet")
    if not attendance_df.empty:
        display_df = attendance_df.copy()
        display_df['date'] = pd.to_datetime(display_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        display_df['check_in_time'] = pd.to_datetime(display_df['check_in_time'], errors='coerce').dt.strftime('%I:%M %p')
        display_df['check_in_time'] = display_df['check_in_time'].fillna('')
        display_df['status'] = display_df['is_present'].apply(lambda x: 'Present' if str(x).lower() in ('true','1','yes') or x is True else 'Absent')
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
        display_df['date'] = pd.to_datetime(display_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        display_df['check_in_time'] = pd.to_datetime(display_df['check_in_time'], errors='coerce').dt.strftime('%I:%M %p')
        display_df['check_in_time'] = display_df['check_in_time'].fillna('')
        display_df['status'] = display_df['is_present'].apply(lambda x: 'Present' if str(x).lower() in ('true','1','yes') or x is True else 'Absent')
        st.dataframe(display_df[['date', 'check_in_time', 'status']].sort_values(by='date', ascending=False), use_container_width=True)
    else:
        st.info("No attendance records found for you.")

def show_add_staff_page():
    st.title("Add New Staff Member")
    if st.button("Back to Dashboard"):
        st.session_state.page = 'owner_dashboard'
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
            users[new_username] = {'password': hash_password(new_password), 'role': 'staff'}
            save_user_data(users)
            st.success(f"Staff member '{new_username}' added successfully!")
            st.info("You can now mark their attendance.")
            st.session_state.page = 'owner_dashboard'
            st.rerun()

def show_mark_attendance_page():
    global attendance_df

    st.title("Mark Attendance")
    if st.button("Back to Dashboard"):
        st.session_state.page = 'owner_dashboard'
        st.rerun()

    st.markdown("---")

    staff_members = [user for user, data in users.items() if data.get('role') == 'staff']

    if not staff_members:
        st.warning("No staff members to mark attendance for. Please add staff first.")
        return

    with st.form(key='mark_attendance_form'):
        selected_staff = st.selectbox("Select Staff Member", staff_members)
        col1, col2 = st.columns([1,1])
        with col1:
            mark_present_button = st.form_submit_button("Mark Present")
        with col2:
            mark_absent_button = st.form_submit_button("Mark Absent")

    if mark_present_button or mark_absent_button:
        if 'date' not in attendance_df.columns:
            attendance_df['date'] = pd.to_datetime(pd.Series([], dtype='datetime64[ns]'))

        attendance_df['date'] = pd.to_datetime(attendance_df['date'], errors='coerce')

        now_ist = datetime.now(INDIA_TIMEZONE)
        current_date = now_ist.date()
        current_time = now_ist.time()

        has_marked_today = False
        if not attendance_df.empty:
            try:
                mask_user = attendance_df['username'] == selected_staff
                mask_date = attendance_df['date'].dt.date == current_date
                has_marked_today = (mask_user & mask_date).any()
            except Exception:
                has_marked_today = False

        if has_marked_today:
            st.warning(f"Attendance for '{selected_staff}' has already been marked for today ({current_date}).")
        else:
            is_present = bool(mark_present_button)
            check_in_str = current_time.strftime('%H:%M:%S') if is_present else ""
            new_record = pd.DataFrame([{
                'username': selected_staff,
                'date': pd.to_datetime(current_date),
                'check_in_time': check_in_str,
                'is_present': is_present
            }])

            attendance_df = pd.concat([attendance_df, new_record], ignore_index=True)
            save_attendance_data(attendance_df)

            if is_present:
                st.success(f"Attendance for '{selected_staff}' marked as Present ({current_date} {check_in_str})!")
            else:
                st.success(f"Attendance for '{selected_staff}' marked as Absent ({current_date})!")

            st.session_state.page = 'owner_dashboard'
            st.rerun()

def perform_logout():
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.page = 'login'
    st.rerun()

def show_logout_button():
    if st.sidebar.button("Logout"):
        perform_logout()

# --- NAVIGATION ---
if not st.session_state.authenticated:
    show_login_page()
else:
    st.sidebar.title("Navigation")
    if st.session_state.role == 'owner':
        if st.sidebar.button("Dashboard", use_container_width=True):
            st.session_state.page = 'owner_dashboard'
            st.rerun()
        if st.sidebar.button("Add Staff", use_container_width=True):
            st.session_state.page = 'add_staff'
            st.rerun()
        if st.sidebar.button("Mark Attendance", use_container_width=True):
            st.session_state.page = 'mark_attendance'
            st.rerun()
    else:
        if st.sidebar.button("My Attendance", use_container_width=True):
            st.session_state.page = 'staff_dashboard'
            st.rerun()

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
