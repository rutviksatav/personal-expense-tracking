import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import psycopg2
from psycopg2 import sql
import os

# Database connection
def get_db_connection():
    """Connect to Heroku Postgres database."""
    DATABASE_URL = os.getenv('DATABASE_URL')
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    """Initialize database tables."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id SERIAL PRIMARY KEY,
            category TEXT,
            subcategory TEXT,
            amount FLOAT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            date TEXT,
            category TEXT,
            amount FLOAT,
            month TEXT,
            year INTEGER
        )
    ''')
    conn.commit()
    # Insert initial budget data if table is empty
    c.execute("SELECT COUNT(*) FROM budgets")
    if c.fetchone()[0] == 0:
        initial_budgets = [
            ('Salary', None, 100000),
            ('Mandatory', 'Home Rent', 13000),
            ('Mandatory', 'Home Electricity', 0),
            ('Mandatory', 'Mutual Funds', 12000),
            ('Mandatory', 'Family Support', 10000),
            ('Mandatory', 'Phone EMI', 5000),
            ('Flexible', 'Food:Groceries', 5000),
            ('Flexible', 'Food:Lunch', 1000),
            ('Flexible', 'Food:Dinner', 1000),
            ('Flexible', 'Food:Weekend/Restaurant', 1000),
            ('Flexible', 'Food:Coffee', 500),
            ('Flexible', 'Shopping:Clothes', 2000),
            ('Flexible', 'Shopping:Perfume', 0),
            ('Flexible', 'Shopping:Skincare', 0),
            ('Flexible', 'Shopping:Accessories/Others', 0),
            ('Flexible', 'Bills & Utilities:Water', 1000),
            ('Flexible', 'Bills & Utilities:Internet/Wifi', 1000),
            ('Flexible', 'Entertainment:Movies', 500),
            ('Flexible', 'Entertainment:Netflix', 200),
            ('Flexible', 'Entertainment:Spotify', 160),
            ('Flexible', 'Entertainment:Hotstar', 100),
            ('Flexible', 'Travel:Office Cab', 2000),
            ('Flexible', 'Travel:Weekend Cabs', 1000),
            ('Flexible', 'Other:Miscellaneous', 500),
            ('Flexible Budget', None, 18260),
            ('Savings', None, 53740)
        ]
        c.executemany("INSERT INTO budgets (category, subcategory, amount) VALUES (%s, %s, %s)", initial_budgets)
        conn.commit()
    conn.close()

class ExpenseTracker:
    def __init__(self):
        init_db()
        self.budgets_df = self.load_budgets()
        self.expenses_df = self.load_expenses()

        # Extract flexible categories for dropdown
        self.flexible_categories = []
        flexible_rows = self.budgets_df[self.budgets_df['category'] == 'Flexible']
        self.flexible_categories = flexible_rows['subcategory'].dropna().tolist()

        # Calculate flexible budget and savings
        self.calculate_flexible_budget()

    def load_budgets(self):
        """Load budgets from database."""
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT category, subcategory, amount FROM budgets", conn)
        conn.close()
        return df

    def load_expenses(self):
        """Load expenses from database."""
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT date, category, amount, month, year FROM expenses", conn)
        conn.close()
        return df if not df.empty else pd.DataFrame(columns=['date', 'category', 'amount', 'month', 'year'])

    def save_expenses(self):
        """Save expenses to database."""
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM expenses")  # Clear existing data
        for _, row in self.expenses_df.iterrows():
            c.execute(
                "INSERT INTO expenses (date, category, amount, month, year) VALUES (%s, %s, %s, %s, %s)",
                (row['date'], row['category'], row['amount'], row['month'], row['year'])
            )
        conn.commit()
        conn.close()

    def add_expense(self, date_val: date, category: str, amount: float):
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        entry = {
            "date": date_val.strftime("%Y-%m-%d"),
            "category": category,
            "amount": amount,
            "month": date_val.strftime("%Y-%m"),
            "year": date_val.year
        }
        new_entry_df = pd.DataFrame([entry])
        self.expenses_df = pd.concat([self.expenses_df, new_entry_df], ignore_index=True)
        self.save_expenses()

    def get_expenses_df(self):
        if self.expenses_df.empty:
            return pd.DataFrame(columns=['date', 'category', 'amount', 'month', 'year'])
        df = self.expenses_df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['year'] = pd.to_numeric(df['year'], errors='coerce')
        return df.dropna(subset=['amount', 'date'])

    def get_budgets(self):
        budgets = {
            "Salary": self.budgets_df[self.budgets_df['category'] == 'Salary']['amount'].iloc[0] if not self.budgets_df[self.budgets_df['category'] == 'Salary'].empty else 0,
            "Mandatory": {
                row['subcategory']: row['amount']
                for _, row in self.budgets_df[self.budgets_df['category'] == 'Mandatory'].iterrows()
                if pd.notna(row['subcategory'])
            },
            "Flexible": {}
        }
        flexible_rows = self.budgets_df[self.budgets_df['category'] == 'Flexible']
        for _, row in flexible_rows.iterrows():
            if pd.notna(row['subcategory']):
                main_cat, sub_cat = row['subcategory'].split(':') if ':' in row['subcategory'] else ('Other', row['subcategory'])
                if main_cat not in budgets['Flexible']:
                    budgets['Flexible'][main_cat] = {}
                budgets['Flexible'][main_cat][sub_cat] = row['amount']
        budgets["Flexible Budget"] = self.budgets_df[self.budgets_df['category'] == 'Flexible Budget']['amount'].iloc[0] if not self.budgets_df[self.budgets_df['category'] == 'Flexible Budget'].empty else 0
        budgets["Savings"] = self.budgets_df[self.budgets_df['category'] == 'Savings']['amount'].iloc[0] if not self.budgets_df[self.budgets_df['category'] == 'Savings'].empty else 0
        return budgets

    def calculate_flexible_budget(self):
        mandatory_total = sum(
            row['amount'] for _, row in self.budgets_df[self.budgets_df['category'] == 'Mandatory'].iterrows()
            if pd.notna(row['subcategory'])
        )
        flexible_total = sum(
            row['amount'] for _, row in self.budgets_df[self.budgets_df['category'] == 'Flexible'].iterrows()
            if pd.notna(row['subcategory'])
        )
        salary = self.budgets_df[self.budgets_df['category'] == 'Salary']['amount'].iloc[0] if not self.budgets_df[self.budgets_df['category'] == 'Salary'].empty else 0
        self.budgets_df.loc[self.budgets_df['category'] == 'Flexible Budget', 'amount'] = flexible_total
        self.budgets_df.loc[self.budgets_df['category'] == 'Savings', 'amount'] = salary - (mandatory_total + flexible_total)
        # Save updated budgets to database
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE budgets SET amount = %s WHERE category = %s", (flexible_total, 'Flexible Budget'))
        c.execute("UPDATE budgets SET amount = %s WHERE category = %s", (salary - (mandatory_total + flexible_total), 'Savings'))
        conn.commit()
        conn.close()

def calculate_statistics(df: pd.DataFrame, tracker) -> dict:
    budgets = tracker.get_budgets()
    mandatory_total = sum(budgets.get("Mandatory", {}).values())
    flexible_budget = budgets.get("Flexible Budget", 0)

    if df.empty:
        return {
            'today_total': 0,
            'monthly_total': 0,
            'flexible_spent': 0,
            'flexible_remaining': flexible_budget,
            'savings': budgets.get("Savings", 0),
            'monthly_by_category': {},
            'top_expenses': []
        }

    current_month = datetime.now().strftime("%Y-%m")
    today = date.today()
    current_month_df = df[df['month'] == current_month]
    today_df = df[df['date'].dt.date == today]

    today_total = today_df['amount'].sum() if not today_df.empty else 0
    monthly_by_category = (
        current_month_df.groupby('category')['amount'].sum().to_dict()
        if not current_month_df.empty else {}
    )
    flexible_spent = sum(
        monthly_by_category.get(cat, 0)
        for cat in tracker.flexible_categories
    )
    flexible_remaining = flexible_budget - flexible_spent
    monthly_total = current_month_df['amount'].sum() if not current_month_df.empty else 0
    top_expenses = current_month_df.sort_values('amount', ascending=False).head(5).to_dict('records')
    savings = budgets.get("Salary", 0) - mandatory_total - flexible_spent

    return {
        'today_total': today_total,
        'monthly_total': monthly_total,
        'flexible_spent': flexible_spent,
        'flexible_remaining': flexible_remaining,
        'savings': savings,
        'monthly_by_category': monthly_by_category,
        'top_expenses': top_expenses
    }

def main():
    st.set_page_config(page_title="Expense Tracker", layout="wide")
    st.title("💰 Personal Expense Tracker")

    if 'tracker' not in st.session_state:
        st.session_state.tracker = ExpenseTracker()

    tracker = st.session_state.tracker
    df_expenses = tracker.get_expenses_df()
    budgets = tracker.get_budgets()
    stats = calculate_statistics(df_expenses, tracker)

    with st.sidebar:
        st.header("💸 Add Expense")
        with st.form("add_expense_form"):
            expense_date = st.date_input("Date", value=date.today())
            category = st.selectbox("Category", tracker.flexible_categories)
            amount = st.number_input("Amount (₹)", min_value=0.0, step=0.01)
            submitted = st.form_submit_button("➕ Add Expense")
            if submitted and amount > 0:
                tracker.add_expense(expense_date, category, amount)
                st.success(f"✅ Added ₹{amount:,.0f} for {category}")
                st.balloons()
                st.session_state['tracker'] = tracker
                df_expenses = tracker.get_expenses_df()
                stats = calculate_statistics(df_expenses, tracker)

    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Expenses", "📈 Analytics"])

    with tab1:
        st.header("📊 Dashboard")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Today's Spending", f"₹{stats['today_total']:,.0f}")
        with col2: st.metric("This Month", f"₹{stats['monthly_total']:,.0f}")
        with col3: st.metric("Flexible Budget Remaining", f"₹{stats['flexible_remaining']:,.0f}")
        with col4: st.metric("Savings", f"₹{stats['savings']:,.0f}")

        if stats['monthly_by_category']:
            st.subheader("💰 Spending by Category")
            budget_data = []
            for cat in tracker.flexible_categories:
                spent = stats['monthly_by_category'].get(cat, 0)
                budget_data.append({'Category': cat, 'Spent': spent})
            budget_df = pd.DataFrame(budget_data)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=budget_df['Category'], y=budget_df['Spent'], name='Spent', marker_color='red'))
            fig.update_layout(title='Spent by Category', xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.header("📝 Expense History")
        if not df_expenses.empty:
            st.dataframe(df_expenses.sort_values('date', ascending=False).reset_index(drop=True))
        else:
            st.info("No expenses recorded yet. Add some from the sidebar!")

    with tab3:
        st.header("📈 Analytics & Insights")
        if not df_expenses.empty:
            st.subheader("Spending by Category")
            fig = px.pie(
                names=list(stats['monthly_by_category'].keys()),
                values=list(stats['monthly_by_category'].values()),
                title="This Month's Spending by Category"
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Top 5 Expenses This Month")
            top_df = pd.DataFrame(stats['top_expenses'])
            st.dataframe(top_df[['date', 'category', 'amount']])

            st.subheader("Monthly Trend (Last 6 Months)")
            df_expenses['month_year'] = df_expenses['date'].dt.to_period('M')
            trend_df = df_expenses.groupby('month_year')['amount'].sum().reset_index()
            trend_df['month_year'] = trend_df['month_year'].astype(str)
            fig2 = px.line(trend_df, x='month_year', y='amount', markers=True, title="Monthly Expense Trend")
            st.plotly_chart(fig2, use_container_width=True)

if __name__ == "__main__":
    main()
