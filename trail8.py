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

# --- UTILITIES ---

def hash_password(password: str) -> str:
    """Hashes a password with a salt."""
    return hashlib.sha256((password + PASSWORD_SALT).encode()).hexdigest()

def load_users():
    """Loads user data from a JSON file."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            try:
                return json.load(f)
            except Exception:
                return {"owner": {"password": hash_password("owner_password"), "role": "owner"}}
    # Default owner account if file doesn't exist
    return {"owner": {"password": hash_password("owner_password"), "role": "owner"}}

def save_users(users):
    """Saves user data to a JSON file."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def load_attendance_data():
    """Loads attendance data from a CSV file and ensures expected columns and datatypes."""
    if os.path.exists(ATTENDANCE_FILE):
        try:
            df = pd.read_csv(ATTENDANCE_FILE, dtype=str)  # read as strings first
        except Exception:
            df = pd.DataFrame(columns=['username','date','check_in_time','check_out_time','is_present'])
        # Ensure columns exist
        expected_cols = ['username','date','check_in_time','check_out_time','is_present']
        for c in expected_cols:
            if c not in df.columns:
                df[c] = pd.NA
        # Convert 'date' column to datetime where possible
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        # Normalize is_present to booleans where possible
        df['is_present'] = df['is_present'].map(lambda v: True if str(v).lower() in ['true','1','yes'] else (False if str(v).lower() in ['false','0','no'] else v))
        return df[expected_cols]
    # Return empty frame with expected columns
    return pd.DataFrame(columns=['username','date','check_in_time','check_out_time','is_present'])

def save_attendance_data(df: pd.DataFrame):
    """Saves attendance data to a CSV file with a clean date format (YYYY-MM-DD)."""
    df_to_save = df.copy()
    # Convert date to YYYY-MM-DD strings (or empty)
    df_to_save['date'] = pd.to_datetime(df_to_save['date'], errors='coerce').dt.date
    # Convert NaT to empty strings for CSV clarity
    df_to_save['date'] = df_to_save['date'].astype(object).where(df_to_save['date'].notna(), '')
    # Ensure times and is_present are strings
    df_to_save['check_in_time'] = df_to_save['check_in_time'].fillna('')
    df_to_save['check_out_time'] = df_to_save['check_out_time'].fillna('')
    df_to_save['is_present'] = df_to_save['is_present'].apply(lambda v: str(bool(v)) if pd.notna(v) and v != '' else '')
    df_to_save.to_csv(ATTENDANCE_FILE, index=False)

def ensure_date_column():
    """Ensure global attendance_df has a 'date' column and it is datetimelike (in-place)."""
    global attendance_df
    if 'date' not in attendance_df.columns:
        attendance_df['date'] = pd.NaT
    attendance_df['date'] = pd.to_datetime(attendance_df['date'], errors='coerce')

def parse_time_str_to_time(s):
    """Parse a time string like 'HH:MM:SS' (or other formats) to a time object. Fallback to current time."""
    try:
        if s is None:
            return datetime.now(INDIA_TIMEZONE).time()
        if isinstance(s, (pd.Timestamp, datetime)):
            return s.time()
        s_str = str(s)
        if s_str.strip() == '' or s_str.lower() == 'nan':
            return datetime.now(INDIA_TIMEZONE).time()
        parsed = pd.to_datetime(s_str, errors='coerce')
        if pd.isna(parsed):
            # final fallback
            return datetime.now(INDIA_TIMEZONE).time()
        return parsed.time()
    except Exception:
        return datetime.now(INDIA_TIMEZONE).time()

# Load data at the start of the app
users = load_users()
attendance_df = load_attendance_data()

# --- LOGIN ---
def login(username, password):
    """Authenticates a user."""
    if username in users and users[username]['password'] == hash_password(password):
        return True, users[username]['role']
    return False, None

# --- DASHBOARDS ---
def show_owner_dashboard():
    """Displays the main owner dashboard with horizontal buttons."""
    global attendance_df
    
    st.title("Owner Dashboard")
    
    # Horizontal button layout
    cols = st.columns(6)
    with cols[0]:
        if st.button("Add Staff"):
            st.session_state.owner_action = "add_staff"
    with cols[1]:
        if st.button("Remove Staff"):
            st.session_state.owner_action = "remove_staff"
    with cols[2]:
        if st.button("Mark New Attendance"):
            st.session_state.owner_action = "mark_attendance"
    with cols[3]:
        if st.button("Edit Existing"):
            st.session_state.owner_action = "edit_attendance"
    with cols[4]:
        if st.button("Delete Records"):
            st.session_state.owner_action = "delete_attendance"
    with cols[5]:
        if st.button("Warnings"):
            st.session_state.owner_action = "warnings"
            
    st.markdown("---")
    
    # Use st.session_state to control which content is shown
    action = st.session_state.get('owner_action', 'view_all')
    
    if action == "add_staff":
        add_staff()
    elif action == "remove_staff":
        remove_staff()
    elif action == "mark_attendance":
        mark_attendance_page()
    elif action == "edit_attendance":
        edit_attendance_page()
    elif action == "delete_attendance":
        delete_attendance_page()
    elif action == "warnings":
        show_warnings()
    elif action == "view_all":
        # Do nothing, the view is shown below
        pass

    # Always show the full attendance sheet at the bottom
    st.markdown("---")
    view_attendance()
    
    # Logout button
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.owner_action = None
        st.rerun()

def show_staff_dashboard(username):
    """Displays the staff dashboard."""
    st.title(f"Welcome, {username}")
    st.subheader("Your Attendance Records")
    df = attendance_df[attendance_df['username'] == username].copy()
    # Make sure date is readable
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date
        st.dataframe(df)
    else:
        st.info("No attendance records yet.")
        
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

# --- STAFF MANAGEMENT ---
def add_staff():
    """Form to add a new staff member."""
    st.subheader("Add New Staff")
    with st.form("add_staff_form"):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Add Staff")
    if submit:
        if not new_username:
            st.error("Enter a username")
            return
        if new_username in users:
            st.error("User already exists")
        else:
            users[new_username] = {"password": hash_password(new_password), "role": "staff"}
            save_users(users)
            st.success(f"Staff {new_username} added!")
            st.session_state.owner_action = "view_all"
            st.rerun()

def remove_staff():
    """Form to remove a staff member."""
    st.subheader("Remove Staff")
    staff_users = [u for u,d in users.items() if d.get("role") == "staff"]
    if not staff_users:
        st.info("No staff to remove")
        return
    selected = st.selectbox("Select Staff to Remove", staff_users)
    if st.button("Remove Selected Staff"):
        del users[selected]
        save_users(users)
        st.success(f"Removed staff {selected}")
        st.session_state.owner_action = "view_all"
        st.rerun()

# --- ATTENDANCE MANAGEMENT ---
def mark_attendance_page():
    """Form to mark new attendance."""
    global attendance_df
    
    st.subheader("Mark New Attendance")
    staff_members = [u for u, d in users.items() if d.get('role') == 'staff']
    if not staff_members:
        st.warning("No staff members available.")
        return

    with st.form("mark_form"):
        selected_staff = st.selectbox("Select Staff", staff_members)
        selected_date = st.date_input("Date", value=datetime.now(INDIA_TIMEZONE).date())
        check_in_time = st.time_input("Check-in Time", value=datetime.now(INDIA_TIMEZONE).time())
        check_out_time = st.time_input("Check-out Time", value=datetime.now(INDIA_TIMEZONE).time())
        is_present = st.checkbox("Present", value=True)
        submit = st.form_submit_button("Submit")

    if submit:
        # Ensure date column is datetime-like before using .dt
        ensure_date_column()

        # Convert selected_date to a datetime.date for comparison
        selected_date_only = selected_date  # already a datetime.date from st.date_input
        mask_user = attendance_df['username'] == selected_staff
        # Safe usage of .dt.date because ensure_date_column() made 'date' datetimelike
        try:
            mask_date = attendance_df['date'].dt.date == selected_date_only
        except Exception:
            # Fallback: create mask of False (no matches)
            mask_date = pd.Series([False] * len(attendance_df), index=attendance_df.index)

        existing_indices = attendance_df[mask_user & mask_date].index.tolist()
        
        if len(existing_indices) > 0:
            idx = existing_indices[0]
            attendance_df.at[idx, 'check_in_time'] = check_in_time.strftime("%H:%M:%S")
            attendance_df.at[idx, 'check_out_time'] = check_out_time.strftime("%H:%M:%S")
            attendance_df.at[idx, 'is_present'] = is_present
            st.success(f"Updated attendance for {selected_staff}")
        else:
            new = pd.DataFrame([{
                'username': selected_staff,
                'date': pd.to_datetime(selected_date_only),
                'check_in_time': check_in_time.strftime("%H:%M:%S"),
                'check_out_time': check_out_time.strftime("%H:%M:%S"),
                'is_present': is_present
            }])
            attendance_df = pd.concat([attendance_df, new], ignore_index=True)
            st.success(f"Marked attendance for {selected_staff}")
            
        save_attendance_data(attendance_df)
        st.session_state.owner_action = "view_all"
        st.rerun()

def edit_attendance_page():
    """Page to edit existing attendance records."""
    global attendance_df

    st.subheader("Edit Existing Attendance Records")

    if attendance_df.empty:
        st.info("No records to edit.")
        return

    # Ensure datetime for 'date'
    ensure_date_column()
    
    # Sort and build readable options
    attendance_df_sorted = attendance_df.sort_values(by='date', ascending=False)
    edit_options = []
    for i, row in attendance_df_sorted.iterrows():
        date_val = pd.to_datetime(row.get('date', pd.NaT), errors='coerce')
        date_str = date_val.strftime('%Y-%m-%d') if not pd.isna(date_val) else 'N/A'
        ci = row.get('check_in_time', '') if pd.notna(row.get('check_in_time', '')) else ''
        co = row.get('check_out_time', '') if pd.notna(row.get('check_out_time', '')) else ''
        uname = row.get('username', '')
        edit_options.append(f"{i} | {uname} | {date_str} | In: {ci} | Out: {co}")

    selected_record = st.selectbox("Select a record", ["---"] + edit_options)

    if selected_record != "---":
        try:
            idx = int(selected_record.split(" | ")[0])
        except Exception:
            st.error("Could not parse selected record index.")
            return

        if idx not in attendance_df.index:
            st.error("Selected record not found.")
            return

        record = attendance_df.loc[idx]

        with st.form(key=f"edit_form_{idx}"):
            new_check_in = st.time_input(
                "Check-in Time",
                value=parse_time_str_to_time(record.get('check_in_time', ''))
            )
            new_check_out = st.time_input(
                "Check-out Time",
                value=parse_time_str_to_time(record.get('check_out_time', ''))
            )
            new_is_present = st.checkbox("Present", value=bool(record.get('is_present', False)))
            update = st.form_submit_button("Update Record")
        if update:
            attendance_df.at[idx, 'check_in_time'] = new_check_in.strftime("%H:%M:%S")
            attendance_df.at[idx, 'check_out_time'] = new_check_out.strftime("%H:%M:%S")
            attendance_df.at[idx, 'is_present'] = new_is_present
            save_attendance_data(attendance_df)
            st.success("Record updated")
            st.session_state.owner_action = "view_all"
            st.rerun()

def delete_attendance_page():
    """Page to delete attendance records."""
    global attendance_df
    
    st.subheader("Delete Attendance Records")
    
    if attendance_df.empty:
        st.info("No records to delete.")
        return

    # Ensure datetime for 'date'
    ensure_date_column()

    def format_row(i):
        try:
            d = attendance_df.loc[i, 'date']
            d = pd.to_datetime(d, errors='coerce')
            d_str = d.strftime('%Y-%m-%d') if not pd.isna(d) else 'N/A'
        except Exception:
            d_str = 'N/A'
        uname = attendance_df.loc[i, 'username'] if 'username' in attendance_df.columns else ''
        return f"{uname} | {d_str}"

    delete_indices = st.multiselect(
        "Select records to delete",
        options=list(attendance_df.index),
        format_func=lambda i: format_row(i)
    )
    if delete_indices and st.button("Delete Selected Records"):
        attendance_df.drop(delete_indices, inplace=True)
        # Optionally reset index to keep things tidy
        attendance_df.reset_index(drop=True, inplace=True)
        save_attendance_data(attendance_df)
        st.success("Selected records deleted")
        st.session_state.owner_action = "view_all"
        st.rerun()

def show_warnings():
    """A placeholder function for displaying warnings."""
    st.subheader("Warnings")
    st.info("No warnings to display at this time.")

def view_attendance():
    """Displays the full attendance sheet."""
    st.subheader("Full Attendance Sheet")
    if attendance_df.empty:
        st.info("No attendance records found.")
    else:
        df_display = attendance_df.copy()
        # Make date readable
        df_display['date'] = pd.to_datetime(df_display['date'], errors='coerce').dt.date
        st.dataframe(df_display)

# --- MAIN APP FLOW ---
def main():
    """Main function to run the Streamlit application."""
    st.title("Attendance System")
    
    # Initialize session state variables
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'role' not in st.session_state:
        st.session_state.role = None
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'owner_action' not in st.session_state:
        st.session_state.owner_action = "view_all" # Default view for owner

    if not st.session_state.logged_in:
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            valid, role = login(username, password)
            if valid:
                st.session_state.logged_in = True
                st.session_state.role = role
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid login")
    else:
        if st.session_state.role == "owner":
            show_owner_dashboard()
        elif st.session_state.role == "staff":
            show_staff_dashboard(st.session_state.username)

if __name__ == "__main__":
    main()
