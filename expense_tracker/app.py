import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import json
import os

# Constants
EXPENSES_FILE = "expenses.json"
BUDGETS_FILE = "budgets.json"

def load_json(file_path):
    """Loads JSON data from a file."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {} if 'budgets' in file_path else []

def save_json(data, file_path):
    """Saves data to a JSON file."""
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

class ExpenseTracker:
    def __init__(self):
        self.expenses = load_json(EXPENSES_FILE)
        self.budgets = load_json(BUDGETS_FILE)
        # Prepare flattened category list
        self.categories = []
        for key, val in self.budgets.get("Mandatory", {}).items():
            self.categories.append(key)
        for cat, subcats in self.budgets.get("Flexible", {}).items():
            for subcat in subcats:
                self.categories.append(subcat)
        # Calculate savings
        self.calculate_savings()

    def add_expense(self, date_val: date, category: str, amount: float):
        """Adds a new expense."""
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        entry = {
            "Date": date_val.strftime("%Y-%m-%d"),
            "Category": category,
            "Amount": amount,
            "Month": date_val.strftime("%Y-%m"),
            "Year": date_val.year
        }
        self.expenses.append(entry)
        save_json(self.expenses, EXPENSES_FILE)

    def get_expenses_df(self):
        """Returns a DataFrame of expenses."""
        if not self.expenses:
            return pd.DataFrame()
        df = pd.DataFrame(self.expenses)
        df['Date'] = pd.to_datetime(df['Date'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        df = df.dropna(subset=['Amount', 'Date'])
        return df

    def get_budgets(self):
        """Returns the current budgets."""
        return self.budgets

    def calculate_savings(self):
        """Calculates remaining budget as savings."""
        salary = self.budgets.get("Salary", 0)
        total_mandatory = sum(self.budgets.get("Mandatory", {}).values())
        total_flexible = sum(
            sum(cat.values()) for cat in self.budgets.get("Flexible", {}).values()
        )
        savings = salary - (total_mandatory + total_flexible)
        self.budgets["Savings"] = savings
        return savings

def calculate_statistics(df: pd.DataFrame, budgets: dict) -> dict:
    """Calculates statistics from the expenses data."""
    if df.empty:
        return {
            'today_total': 0,
            'monthly_total': 0,
            'total_budget': budgets.get("Salary", 0),
            'budget_remaining': budgets.get("Salary", 0),
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

    monthly_total = current_month_df['Amount'].sum() if not current_month_df.empty else 0
    total_budget = budgets.get("Salary", 0)
    top_expenses = current_month_df.sort_values('Amount', ascending=False).head(5).to_dict('records')

    return {
        'today_total': today_total,
        'monthly_total': monthly_total,
        'total_budget': total_budget,
        'budget_remaining': total_budget - monthly_total,
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
    stats = calculate_statistics(df_expenses, budgets)

    # Sidebar: Add Expense
    with st.sidebar:
        st.header("💸 Add Expense")
        with st.form("add_expense_form"):
            expense_date = st.date_input("Date", value=date.today())
            category = st.selectbox("Category", tracker.categories)
            amount = st.number_input("Amount (₹)", min_value=0.0, step=0.01)
            submitted = st.form_submit_button("➕ Add Expense")

            if submitted and amount > 0:
                tracker.add_expense(expense_date, category, amount)
                st.success(f"✅ Added ₹{amount:,.0f} for {category}")
                st.balloons()
                st.session_state['tracker'] = tracker

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Expenses", "📈 Analytics"])

    # Dashboard Tab
    with tab1:
        st.header("📊 Dashboard")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: st.metric("Today's Spending", f"₹{stats['today_total']:,.0f}")
        with col2: st.metric("This Month", f"₹{stats['monthly_total']:,.0f}")
        remaining = stats['budget_remaining']
        remaining_pct = (remaining / budgets["Salary"] * 100) if budgets["Salary"] > 0 else 0
        with col3: st.metric("Budget Remaining", f"₹{remaining:,.0f}", f"{remaining_pct:.0f}%")
        with col4: st.metric("Savings", f"₹{budgets.get('Savings', 0):,.0f}")
        with col5: st.metric("Savings Rate", f"{(budgets.get('Savings',0)/budgets['Salary']*100):.1f}%")

        # Budget vs Actual Chart
        if stats['monthly_by_category']:
            st.subheader("💰 Spending by Category")
            budget_data = []
            for cat in tracker.categories:
                spent = stats['monthly_by_category'].get(cat, 0)
                budget_data.append({
                    'Category': cat,
                    'Budget': 0,  # Already included in Savings calculation
                    'Spent': spent
                })
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
            st.dataframe(top_df[['Date','Category','Amount']])

            st.subheader("Monthly Trend (Last 6 Months)")
            df_expenses['Month_Year'] = df_expenses['Date'].dt.to_period('M')
            trend_df = df_expenses.groupby('Month_Year')['Amount'].sum().reset_index()
            trend_df['Month_Year'] = trend_df['Month_Year'].astype(str)
            fig2 = px.line(trend_df, x='Month_Year', y='Amount', markers=True, title="Monthly Expense Trend")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No expense data to display analytics yet.")

if __name__ == "__main__":
    main()
