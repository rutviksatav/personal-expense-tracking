import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date

# Constants
EXPENSES_FILE = "expenses.csv"  # Changed to CSV
BUDGETS_FILE = "budgets.csv"

def load_budgets_csv(file_path):
    """Load budgets from CSV file."""
    try:
        df = pd.read_csv(file_path)
        if set(df.columns) != {'Category', 'Subcategory', 'Amount'}:
            raise ValueError("CSV must have 'Category', 'Subcategory', and 'Amount' columns")
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=['Category', 'Subcategory', 'Amount'])

def load_expenses_csv(file_path):
    """Load expenses from CSV file."""
    try:
        df = pd.read_csv(file_path)
        if set(df.columns) != {'Date', 'Category', 'Amount', 'Month', 'Year'}:
            raise ValueError("CSV must have 'Date', 'Category', 'Amount', 'Month', 'Year' columns")
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=['Date', 'Category', 'Amount', 'Month', 'Year'])

def save_expenses_csv(df, file_path):
    """Save expenses to CSV file."""
    df.to_csv(file_path, index=False)

class ExpenseTracker:
    def __init__(self):
        self.budgets_df = load_budgets_csv(BUDGETS_FILE)
        self.expenses_df = load_expenses_csv(EXPENSES_FILE)

        # Extract flexible categories for dropdown
        self.flexible_categories = []
        flexible_rows = self.budgets_df[self.budgets_df['Category'] == 'Flexible']
        self.flexible_categories = flexible_rows['Subcategory'].dropna().tolist()

        # Calculate flexible budget and savings
        self.calculate_flexible_budget()

    def add_expense(self, date_val: date, category: str, amount: float):
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        entry = {
            "Date": date_val.strftime("%Y-%m-%d"),
            "Category": category,
            "Amount": amount,
            "Month": date_val.strftime("%Y-%m"),
            "Year": date_val.year
        }
        # Append new expense to DataFrame
        new_entry_df = pd.DataFrame([entry])
        self.expenses_df = pd.concat([self.expenses_df, new_entry_df], ignore_index=True)
        save_expenses_csv(self.expenses_df, EXPENSES_FILE)

    def get_expenses_df(self):
        if self.expenses_df.empty:
            return pd.DataFrame(columns=['Date', 'Category', 'Amount', 'Month', 'Year'])
        df = self.expenses_df.copy()
        df['Date'] = pd.to_datetime(df['Date'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
        return df.dropna(subset=['Amount', 'Date'])

    def get_budgets(self):
        # Convert budgets DataFrame to a dictionary for compatibility
        budgets = {
            "Salary": self.budgets_df[self.budgets_df['Category'] == 'Salary']['Amount'].iloc[0] if not self.budgets_df[self.budgets_df['Category'] == 'Salary'].empty else 0,
            "Mandatory": {
                row['Subcategory']: row['Amount']
                for _, row in self.budgets_df[self.budgets_df['Category'] == 'Mandatory'].iterrows()
                if pd.notna(row['Subcategory'])
            },
            "Flexible": {}
        }
        # Organize flexible subcategories
        flexible_rows = self.budgets_df[self.budgets_df['Category'] == 'Flexible']
        for _, row in flexible_rows.iterrows():
            if pd.notna(row['Subcategory']):
                main_cat, sub_cat = row['Subcategory'].split(':') if ':' in row['Subcategory'] else ('Other', row['Subcategory'])
                if main_cat not in budgets['Flexible']:
                    budgets['Flexible'][main_cat] = {}
                budgets['Flexible'][main_cat][sub_cat] = row['Amount']
        budgets["Flexible Budget"] = self.budgets_df[self.budgets_df['Category'] == 'Flexible Budget']['Amount'].iloc[0] if not self.budgets_df[self.budgets_df['Category'] == 'Flexible Budget'].empty else 0
        budgets["Savings"] = self.budgets_df[self.budgets_df['Category'] == 'Savings']['Amount'].iloc[0] if not self.budgets_df[self.budgets_df['Category'] == 'Savings'].empty else 0
        return budgets

    def calculate_flexible_budget(self):
        mandatory_total = sum(
            row['Amount'] for _, row in self.budgets_df[self.budgets_df['Category'] == 'Mandatory'].iterrows()
            if pd.notna(row['Subcategory'])
        )
        flexible_total = sum(
            row['Amount'] for _, row in self.budgets_df[self.budgets_df['Category'] == 'Flexible'].iterrows()
            if pd.notna(row['Subcategory'])
        )
        salary = self.budgets_df[self.budgets_df['Category'] == 'Salary']['Amount'].iloc[0] if not self.budgets_df[self.budgets_df['Category'] == 'Salary'].empty else 0
        self.budgets_df.loc[self.budgets_df['Category'] == 'Flexible Budget', 'Amount'] = flexible_total
        self.budgets_df.loc[self.budgets_df['Category'] == 'Savings', 'Amount'] = salary - (mandatory_total + flexible_total)
        # Save updated budgets to CSV
        self.budgets_df.to_csv(BUDGETS_FILE, index=False)

def calculate_statistics(df: pd.DataFrame, tracker) -> dict:
    """Calculates statistics from the expenses data."""
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
    current_month_df = df[df['Month'] == current_month]
    today_df = df[df['Date'].dt.date == today]

    today_total = today_df['Amount'].sum() if not today_df.empty else 0

    monthly_by_category = (
        current_month_df.groupby('Category')['Amount'].sum().to_dict()
        if not current_month_df.empty else {}
    )

    # Calculate spent in flexible categories only
    flexible_spent = sum(
        monthly_by_category.get(cat, 0)
        for cat in tracker.flexible_categories
    )
    flexible_remaining = flexible_budget - flexible_spent

    monthly_total = current_month_df['Amount'].sum() if not current_month_df.empty else 0
    top_expenses = current_month_df.sort_values('Amount', ascending=False).head(5).to_dict('records')

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

    # Initialize tracker
    if 'tracker' not in st.session_state:
        st.session_state.tracker = ExpenseTracker()

    tracker = st.session_state.tracker
    df_expenses = tracker.get_expenses_df()
    budgets = tracker.get_budgets()
    stats = calculate_statistics(df_expenses, tracker)

    # Sidebar: Add Expense
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

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Expenses", "📈 Analytics"])

    # Dashboard
    with tab1:
        st.header("📊 Dashboard")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Today's Spending", f"₹{stats['today_total']:,.0f}")
        with col2: st.metric("This Month", f"₹{stats['monthly_total']:,.0f}")
        with col3: st.metric("Flexible Budget Remaining", f"₹{stats['flexible_remaining']:,.0f}")
        with col4: st.metric("Savings", f"₹{stats['savings']:,.0f}")

        # Spending by category
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

    # Expenses Tab
    with tab2:
        st.header("📝 Expense History")
        if not df_expenses.empty:
            st.dataframe(df_expenses.sort_values('Date', ascending=False).reset_index(drop=True))
        else:
            st.info("No expenses recorded yet. Add some from the sidebar!")

    # Analytics Tab
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
            st.dataframe(top_df[['Date', 'Category', 'Amount']])

            st.subheader("Monthly Trend (Last 6 Months)")
            df_expenses['Month_Year'] = df_expenses['Date'].dt.to_period('M')
            trend_df = df_expenses.groupby('Month_Year')['Amount'].sum().reset_index()
            trend_df['Month_Year'] = trend_df['Month_Year'].astype(str)
            fig2 = px.line(trend_df, x='Month_Year', y='Amount', markers=True, title="Monthly Expense Trend")
            st.plotly_chart(fig2, use_container_width=True)

if __name__ == "__main__":
    main()
