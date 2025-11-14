# nutrimate_app.py
# Nutrimate - Enhanced Streamlit Personal Nutrition Tracker
# Features: user login (username only), food database (editable), custom foods, meal logging,
# daily calorie goal, charts, CSV export, food add/delete, meal delete, dynamic updates.

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import altair as alt
import io

# ----------------------
# Constants & Example Food DB
# ----------------------
DB_PATH = "nutrimate.db"

DEFAULT_FOODS = [
    ("Apple", 95, 0.3, 25, 0.5),
    ("Banana", 105, 1.3, 27, 0.3),
    ("Rice (1 cup)", 200, 4.3, 45, 0.4),
    ("Chapati", 120, 3.6, 20, 0.9),
    ("Egg (large)", 78, 6.0, 0.4, 5.5),
    ("Milk (1 glass)", 150, 8.0, 12, 8.0),
    ("Chicken (100g)", 239, 27.0, 0, 14.0),
    ("Fish (100g)", 206, 22.0, 0, 12.0),
    ("Salad (bowl)", 80, 2.0, 10, 5.0),
    ("Orange", 62, 1.2, 15, 0.2),
    ("Yogurt (1 cup)", 150, 8.5, 11, 8.0),
    ("Peanut Butter (2 tbsp)", 190, 7, 6, 16),
    ("Oats (1 cup cooked)", 150, 5, 27, 3),
    ("Almonds (10 pcs)", 70, 2.5, 2.5, 6),
    ("Broccoli (1 cup)", 55, 4.5, 11, 0.5),
]

# ----------------------
# Database helpers
# ----------------------
def init_db(conn: sqlite3.Connection):
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            daily_goal INTEGER DEFAULT 2000
        )""")
    c.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            calories INTEGER,
            protein REAL,
            carbs REAL,
            fat REAL
        )""")
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            food_id INTEGER,
            custom_name TEXT,
            quantity INTEGER,
            calories INTEGER,
            protein REAL,
            carbs REAL,
            fat REAL,
            notes TEXT,
            timestamp TEXT,
            meal_type TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(food_id) REFERENCES foods(id)
        )""")
    conn.commit()

    # Populate default foods if empty
    c.execute("SELECT COUNT(*) FROM foods")
    count = c.fetchone()[0]
    if count == 0:
        c.executemany(
            "INSERT INTO foods (name, calories, protein, carbs, fat) VALUES (?, ?, ?, ?, ?)",
            DEFAULT_FOODS,
        )
        conn.commit()

@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    init_db(conn)
    return conn

# ----------------------
# User management
# ----------------------
def get_or_create_user(conn, username: str):
    c = conn.cursor()
    c.execute("SELECT id, username, daily_goal FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    if row:
        return {"id": row[0], "username": row[1], "daily_goal": row[2]}
    c.execute("INSERT INTO users (username) VALUES (?)", (username,))
    conn.commit()
    return get_or_create_user(conn, username)

def update_daily_goal(conn, user_id: int, new_goal: int):
    c = conn.cursor()
    c.execute("UPDATE users SET daily_goal = ? WHERE id = ?", (new_goal, user_id))
    conn.commit()

# ----------------------
# Food & Logging helpers
# ----------------------
def fetch_foods(conn):
    return pd.read_sql_query("SELECT * FROM foods ORDER BY name", conn)

def add_food_to_db(conn, name, calories, protein=0, carbs=0, fat=0):
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO foods (name, calories, protein, carbs, fat) VALUES (?, ?, ?, ?, ?)",
            (name, int(calories), float(protein), float(carbs), float(fat)),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def delete_food_from_db(conn, name):
    c = conn.cursor()
    c.execute("DELETE FROM foods WHERE name = ?", (name,))
    conn.commit()

def log_meal(conn, user_id, food_id, custom_name, quantity, calories, protein, carbs, fat, notes, meal_type):
    c = conn.cursor()
    ts = datetime.now().isoformat()
    c.execute(
        "INSERT INTO logs (user_id, food_id, custom_name, quantity, calories, protein, carbs, fat, notes, timestamp, meal_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, food_id, custom_name, quantity, calories, protein, carbs, fat, notes, ts, meal_type),
    )
    conn.commit()

def fetch_logs_for_user(conn, user_id, start_date=None, end_date=None):
    q = "SELECT * FROM logs WHERE user_id = ?"
    params = [user_id]
    if start_date:
        q += " AND date(timestamp) >= date(?)"
        params.append(start_date)
    if end_date:
        q += " AND date(timestamp) <= date(?)"
        params.append(end_date)
    q += " ORDER BY timestamp DESC"
    df = pd.read_sql_query(q, conn, params=params, parse_dates=["timestamp"])
    return df

def delete_log(conn, log_id):
    c = conn.cursor()
    c.execute("DELETE FROM logs WHERE id = ?", (log_id,))
    conn.commit()

# ----------------------
# Calculations & Charts
# ----------------------
def daily_summary(df: pd.DataFrame):
    if df.empty:
        return {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    return {
        "calories": int(df["calories"].sum()),
        "protein": float(df["protein"].sum()),
        "carbs": float(df["carbs"].sum()),
        "fat": float(df["fat"].sum()),
    }

def plot_calories_over_time(df: pd.DataFrame):
    if df.empty:
        st.info("No data to plot yet.")
        return
    df_plot = df.copy()
    df_plot["date"] = pd.to_datetime(df_plot["timestamp"]).dt.date
    daily = df_plot.groupby("date")["calories"].sum().reset_index()
    chart = alt.Chart(daily).mark_line(point=True).encode(
        x=alt.X("date:T", title="Date"),
        y=alt.Y("calories:Q", title="Calories"),
        tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("calories:Q", title="Calories")],
    ).properties(width=700, height=300)
    st.altair_chart(chart, use_container_width=True)

# ----------------------
# Export helpers
# ----------------------
def export_logs_csv(df: pd.DataFrame):
    if df.empty:
        return None
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()

# ----------------------
# Streamlit App UI
# ----------------------
st.set_page_config(page_title="Nutrimate", page_icon="🥗", layout="wide")
conn = get_conn()

# --- Sidebar ---
with st.sidebar:
    st.title("🥗 Nutrimate")
    st.write("Personal Nutrition Tracker")
    if "user" not in st.session_state:
        st.session_state.user = None
    username = st.text_input("Enter your name (to login):", value="" if not st.session_state.user else st.session_state.user["username"])
    if st.button("Login / Create"):
        if username.strip() == "":
            st.error("Please enter a name to continue.")
        else:
            user = get_or_create_user(conn, username.strip())
            st.session_state.user = user
            st.success(f"Welcome, {user['username']}!")
    if st.session_state.user:
        st.markdown("---")
        st.write(f"**Logged in as:** {st.session_state.user['username']}")
        st.write(f"**Daily calorie goal:** {st.session_state.user['daily_goal']} kcal")
        st.markdown("---")
    page = st.radio("Navigate", ["Dashboard", "Log Meal", "History", "Foods", "Settings", "Export"], index=0)
    st.caption("Built with ❤️ using Streamlit")

if not st.session_state.get("user") and page not in ["Foods", "Export"]:
    st.header("Please login to continue")
    st.info("Enter a name in the sidebar and press 'Login / Create' to get started.")
    st.stop()

user = st.session_state.get("user")
user_id = user["id"] if user else None

# ----------------------
# Pages: Dashboard, Log Meal, History, Foods, Settings, Export
# ----------------------

# --- Dashboard ---
if page == "Dashboard":
    st.header("📊 Dashboard")
    today_str = date.today().isoformat()
    df_today = fetch_logs_for_user(conn, user_id, start_date=today_str, end_date=today_str)
    summary = daily_summary(df_today)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Calories (today)", f"{summary['calories']} kcal", delta=f"{summary['calories'] - user['daily_goal']} kcal")
    col2.metric("Protein (g)", f"{summary['protein']:.1f} g")
    col3.metric("Carbs (g)", f"{summary['carbs']:.1f} g")
    col4.metric("Fat (g)", f"{summary['fat']:.1f} g")
    st.subheader("💡 Recommendation")
    if summary['calories'] < int(user['daily_goal'] * 0.9):
        st.info("You're under your daily goal — consider a balanced snack.")
    elif summary['calories'] <= int(user['daily_goal'] * 1.1):
        st.success("Great! You're within your daily calorie goal.")
    else:
        st.warning("You're above your daily calorie goal. Consider lighter meals.")
    st.markdown("---")
    st.subheader("Recent logs")
    if not df_today.empty:
        foods_df = fetch_foods(conn)
        food_dict = dict(zip(foods_df['id'], foods_df['name']))
        df_today['food_name'] = df_today.apply(lambda row: food_dict.get(row['food_id'], row['custom_name'] if row['custom_name'] else "Deleted Food"), axis=1)
        st.table(df_today[['timestamp','meal_type','food_name','quantity','calories']].head(10))
    else:
        st.write("No logs for today yet.")
    st.markdown("---")
    st.subheader("Calories over last 30 days")
    df_30 = fetch_logs_for_user(conn, user_id, start_date=(date.today().replace(day=1)).isoformat())
    plot_calories_over_time(df_30)

# --- Log Meal ---
elif page == "Log Meal":
    st.header("🍽️ Log a Meal")
    foods_df = fetch_foods(conn)
    food_options = list(foods_df['name'])
    col1, col2 = st.columns([2,1])
    with col1:
        meal_type = st.selectbox("Meal type", ["Breakfast","Lunch","Snack","Dinner","Other"])
        food_choice = st.selectbox("Choose food (or select 'Custom'):", ["Select..."] + food_options + ["Custom"])
        quantity = st.number_input("Quantity / Servings:", min_value=0, value=0, step=1)
        notes = st.text_area("Notes (optional):", max_chars=200)
    with col2:
        st.write("### Quick Nutrition")
        if food_choice in food_options:
            row = foods_df[foods_df['name'] == food_choice].iloc[0]
            st.write(f"**{row['name']}** — {int(row['calories'])} kcal / serving")
            st.write(f"Protein: {row['protein']} g | Carbs: {row['carbs']} g | Fat: {row['fat']} g")
        elif food_choice == "Custom":
            st.write("Create a custom food for this entry")
            custom_name = st.text_input("Custom food name:")
            c_cal = st.number_input("Calories per serving:", min_value=0, value=100, step=1)
            c_pro = st.number_input("Protein (g):", min_value=0.0, value=0.0, step=0.1)
            c_car = st.number_input("Carbs (g):", min_value=0.0, value=0.0, step=0.1)
            c_fat = st.number_input("Fat (g):", min_value=0.0, value=0.0, step=0.1)
        else:
            st.write("Select a food to see nutrition details.")
    if st.button("Add to Log"):
        if food_choice in food_options:
            food_id = int(foods_df[foods_df['name'] == food_choice]['id'].iloc[0])
            row = foods_df[foods_df['id'] == food_id].iloc[0]
            calories = int(row['calories']) * int(quantity)
            protein = float(row['protein']) * int(quantity)
            carbs = float(row['carbs']) * int(quantity)
            fat = float(row['fat']) * int(quantity)
            log_meal(conn, user_id, food_id, None, quantity, calories, protein, carbs, fat, notes, meal_type)
            st.success(f"Added {quantity} x {food_choice} ({calories} kcal)")
        elif food_choice == "Custom":
            if not custom_name:
                st.error("Enter a name for the custom food.")
            else:
                calories = int(c_cal) * int(quantity)
                protein = float(c_pro) * int(quantity)
                carbs = float(c_car) * int(quantity)
                fat = float(c_fat) * int(quantity)
                log_meal(conn, user_id, None, custom_name, quantity, calories, protein, carbs, fat, notes, meal_type)
                st.success(f"Added {quantity} x {custom_name} ({calories} kcal)")
        else:
            st.error("Choose a valid food or create a custom one.")

# --- History & Delete Logged Meal ---
elif page == "History":
    st.header("📚 History & Insights")
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start date", value=date.today().replace(day=1))
    with col2:
        end = st.date_input("End date", value=date.today())
    df_logs = fetch_logs_for_user(conn, user_id, start_date=start.isoformat(), end_date=end.isoformat())
    if df_logs.empty:
        st.write("No logs in this range.")
    else:
        foods_df = fetch_foods(conn)
        food_dict = dict(zip(foods_df['id'], foods_df['name']))
        df_logs['food_name'] = df_logs.apply(lambda row: food_dict.get(row['food_id'], row['custom_name'] if row['custom_name'] else "Deleted Food"), axis=1)
        st.dataframe(df_logs[['id','timestamp','meal_type','food_name','quantity','calories','protein','carbs','fat','notes']])
        # Delete logged meal
        st.markdown("---")
        st.subheader("Delete a logged meal")
        log_options = {f"{row['timestamp']} | {row['food_name']} | {row['quantity']} servings": row['id'] for _, row in df_logs.iterrows()}
        if log_options:
            selected_log = st.selectbox("Select a meal to delete", list(log_options.keys()))
            if st.button("Delete selected meal"):
                delete_log(conn, log_options[selected_log])
                st.success("Meal deleted successfully.")
        st.markdown("---")
        s = daily_summary(df_logs)
        st.write(f"Total calories in range: **{s['calories']} kcal**")
        st.write(f"Protein: **{s['protein']:.1f} g**, Carbs: **{s['carbs']:.1f} g**, Fat: **{s['fat']:.1f} g**")
        st.subheader("Calories trend")
        plot_calories_over_time(df_logs)

# --- Foods Page ---
elif page == "Foods":
    st.header("🍏 Food Database")
    foods_df = fetch_foods(conn)
    st.dataframe(foods_df[['id','name','calories','protein','carbs','fat']])
    st.markdown("---")
    # Add new food
    st.subheader("Add a new food")
    with st.form("add_food_form"):
        new_name = st.text_input("Food name")
        new_cal = st.number_input("Calories per serving", min_value=0, value=100, step=1)
        new_pro = st.number_input("Protein (g)", min_value=0.0, value=0.0, step=0.1)
        new_car = st.number_input("Carbs (g)", min_value=0.0, value=0.0, step=0.1)
        new_fat = st.number_input("Fat (g)", min_value=0.0, value=0.0, step=0.1)
        if st.form_submit_button("Add food"):
            if new_name.strip() == "":
                st.error("Enter a food name.")
            else:
                ok = add_food_to_db(conn, new_name.strip(), new_cal, new_pro, new_car, new_fat)
                if ok:
                    st.success(f"Added {new_name} to food database.")
                else:
                    st.error("Food already exists or could not be added.")
    # Delete food
    st.markdown("---")
    st.subheader("Delete a food")
    if not foods_df.empty:
        food_to_delete = st.selectbox("Select food to delete", foods_df['name'])
        if st.button("Delete selected food"):
            delete_food_from_db(conn, food_to_delete)
            st.success(f"{food_to_delete} removed from food database.")

# --- Settings ---
elif page == "Settings":
    st.header("⚙️ Settings")
    new_goal = st.number_input("Daily calorie goal (kcal)", min_value=500, max_value=10000, value=int(user['daily_goal']), step=50)
    if st.button("Update goal"):
        update_daily_goal(conn, user_id, int(new_goal))
        st.session_state.user = get_or_create_user(conn, user['username'])
        st.success("Daily goal updated.")
    st.markdown("---")
    if st.button("Delete all my logs (dangerous)"):
        c = conn.cursor()
        c.execute("DELETE FROM logs WHERE user_id = ?", (user_id,))
        conn.commit()
        st.warning("All logs deleted for your account.")

# --- Export ---
elif page == "Export":
    st.header("📤 Export & Backup")
    if user:
        df_all = fetch_logs_for_user(conn, user_id)
        foods_df = fetch_foods(conn)
        food_dict = dict(zip(foods_df['id'], foods_df['name']))
        df_all['food_name'] = df_all.apply(lambda row: food_dict.get(row['food_id'], row['custom_name'] if row['custom_name'] else "Deleted Food"), axis=1)
        csv = export_logs_csv(df_all)
        st.write("Download your logs as CSV for backup or analysis.")
        if csv:
            st.download_button("Download CSV", data=csv, file_name=f"nutrimate_logs_{user['username']}.csv", mime="text/csv")
        else:
            st.info("No logs to export yet.")
    st.markdown("---")
    st.subheader("Export food database")
    foods_df = fetch_foods(conn)
    buf = io.StringIO()
    foods_df.to_csv(buf, index=False)
    st.download_button("Download foods CSV", data=buf.getvalue(), file_name="nutrimate_foods.csv", mime="text/csv")
