import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

DB_FILE = "bank.db"
ADMIN_PASSWORD = "shyam123"   # <-- set your own secure password here


# --------------------------
# Database layer (CRUD)
# -------------------------
class BankDB:
    def __init__(self, db_file=DB_FILE):
        self.conn = sqlite3.connect(db_file)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.create_schema()

    def create_schema(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            type TEXT NOT NULL, -- "DEPOSIT", "WITHDRAW", "TRANSFER_IN", "TRANSFER_OUT"
            amount REAL NOT NULL,
            timestamp TEXT NOT NULL,
            note TEXT,
            related_account_id INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        """)
        self.conn.commit()

    # --- Account operations ---
    def create_account(self, name: str, initial_balance: float = 0.0):
        if not name.strip():
            raise ValueError("Account name cannot be empty.")
        if initial_balance < 0:
            raise ValueError("Initial balance cannot be negative.")
        ts = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO accounts (name, balance, created_at) VALUES (?,?,?)",
            (name.strip(), float(initial_balance), ts)
        )
        acc_id = cur.lastrowid
        if initial_balance > 0:
            self._add_tx(acc_id, "DEPOSIT", float(initial_balance), "Initial deposit")
        self.conn.commit()
        return acc_id

    def get_account(self, account_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, balance, created_at FROM accounts WHERE id = ?", (account_id,))
        return cur.fetchone()

    def search_accounts(self, query: str = ""):
        cur = self.conn.cursor()
        q = f"%{query.strip()}%"
        cur.execute("""
            SELECT id, name, balance, created_at
            FROM accounts
            WHERE name LIKE ? OR CAST(id AS TEXT) LIKE ?
            ORDER BY id ASC
        """, (q, q))
        return cur.fetchall()

    def delete_account(self, account_id: int):
        # Prevent deleting account that still has money (optional business rule)
        acc = self.get_account(account_id)
        if not acc:
            raise ValueError("Account not found.")
        if acc[2] != 0:
            raise ValueError("Cannot delete account with non-zero balance. Please withdraw/transfer first.")
        cur = self.conn.cursor()
        cur.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self.conn.commit()

    # --- Transaction operations ---
    def deposit(self, account_id: int, amount: float, note: str = ""):
        if amount <= 0:
            raise ValueError("Deposit amount must be positive.")
        acc = self.get_account(account_id)
        if not acc:
            raise ValueError("Account not found.")
        new_balance = acc[2] + amount
        cur = self.conn.cursor()
        cur.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, account_id))
        self._add_tx(account_id, "DEPOSIT", amount, note)
        self.conn.commit()
        return new_balance

    def withdraw(self, account_id: int, amount: float, note: str = ""):
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive.")
        acc = self.get_account(account_id)
        if not acc:
            raise ValueError("Account not found.")
        if acc[2] < amount:
            raise ValueError("Insufficient balance.")
        new_balance = acc[2] - amount
        cur = self.conn.cursor()
        cur.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, account_id))
        self._add_tx(account_id, "WITHDRAW", amount, note)
        self.conn.commit()
        return new_balance

    def transfer(self, from_id: int, to_id: int, amount: float, note: str = ""):
        if from_id == to_id:
            raise ValueError("Cannot transfer to the same account.")
        if amount <= 0:
            raise ValueError("Transfer amount must be positive.")
        acc_from = self.get_account(from_id)
        acc_to = self.get_account(to_id)
        if not acc_from or not acc_to:
            raise ValueError("Source or destination account not found.")
        if acc_from[2] < amount:
            raise ValueError("Insufficient balance in source account.")

        cur = self.conn.cursor()
        # Update balances
        new_from_balance = acc_from[2] - amount
        new_to_balance = acc_to[2] + amount
        cur.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_from_balance, from_id))
        cur.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_to_balance, to_id))

        # Add paired transactions
        self._add_tx(from_id, "TRANSFER_OUT", amount, note, related_account_id=to_id)
        self._add_tx(to_id, "TRANSFER_IN", amount, note, related_account_id=from_id)
        self.conn.commit()
        return new_from_balance, new_to_balance

    def list_transactions(self, account_id: int, limit: int = 50):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, type, amount, timestamp, note, related_account_id
            FROM transactions
            WHERE account_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (account_id, limit))
        return cur.fetchall()

    def _add_tx(self, account_id: int, tx_type: str, amount: float, note: str = "", related_account_id: int | None = None):
        ts = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO transactions (account_id, type, amount, timestamp, note, related_account_id)
            VALUES (?,?,?,?,?,?)
        """, (account_id, tx_type, float(amount), ts, note.strip() if note else None, related_account_id))


# --------------------------
# GUI layer
# --------------------------
class BankApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shyam Capital & Finance")
        self.geometry("960x640")
        self.db = BankDB()

        # Notebook (tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.accounts_tab = ttk.Frame(self.notebook)
        self.deposit_tab = ttk.Frame(self.notebook)
        self.withdraw_tab = ttk.Frame(self.notebook)
        self.transfer_tab = ttk.Frame(self.notebook)
        self.transactions_tab = ttk.Frame(self.notebook)
        self.admin_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.accounts_tab, text="Accounts")
        self.notebook.add(self.deposit_tab, text="Deposit")
        self.notebook.add(self.withdraw_tab, text="Withdraw")
        self.notebook.add(self.transfer_tab, text="Transfer")
        self.notebook.add(self.transactions_tab, text="Transactions")

        # Admin tab is NOT added yet until password is entered
        self.admin_unlocked = False

        # Build tabs
        self._setup_accounts_tab()
        self._setup_deposit_tab()
        self._setup_withdraw_tab()
        self._setup_transfer_tab()
        self._setup_transactions_tab()

        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
        self.status_label = tk.Label(self, textvariable=self.status_var, anchor="w",
                                     relief="sunken", bg="#f0f0f0", padx=8)
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)

        # Admin login frame
        self._setup_admin_login()

    # ---------------- Status utilities ----------------
    def set_status(self, msg, status="info"):
        colors = {"info": "#f0f0f0", "success": "#d6f5d6", "warning": "#ffe8b3", "error": "#f9c2c2"}
        self.status_var.set(msg)
        self.status_label.config(bg=colors.get(status, "#f0f0f0"))

    # ---------------- Admin Login ----------------
    def _setup_admin_login(self):
        login_frame = ttk.LabelFrame(self, text="Admin Login")
        login_frame.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(login_frame, text="Enter Admin Password:").grid(row=0, column=0, padx=6, pady=6)
        self.admin_pass_var = tk.StringVar()
        ttk.Entry(login_frame, textvariable=self.admin_pass_var, show="*").grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(login_frame, text="Unlock Admin", command=self.unlock_admin).grid(row=0, column=2, padx=6, pady=6)

    def unlock_admin(self):
        if self.admin_pass_var.get() == ADMIN_PASSWORD:
            if not self.admin_unlocked:
                self.notebook.add(self.admin_tab, text="Admin")
                self._setup_admin_tab()
                self.admin_unlocked = True
                self.set_status("Admin tab unlocked successfully.", "success")
        else:
            self.set_status("Incorrect password. Access denied.", "error")


    # ---------------- Accounts Tab ----------------
    def _setup_accounts_tab(self):
        frm = self.accounts_tab

        # Create account
        create_frame = ttk.LabelFrame(frm, text="Create account")
        create_frame.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(create_frame, text="Name:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.acc_name_var = tk.StringVar()
        ttk.Entry(create_frame, textvariable=self.acc_name_var, width=30).grid(row=0, column=1, padx=6, pady=6)

        ttk.Label(create_frame, text="Initial balance:").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        self.acc_init_var = tk.StringVar(value="0")
        ttk.Entry(create_frame, textvariable=self.acc_init_var, width=15).grid(row=0, column=3, padx=6, pady=6)

        ttk.Button(create_frame, text="Create", command=self.create_account).grid(row=0, column=4, padx=6, pady=6)

        # Search and list
        list_frame = ttk.LabelFrame(frm, text="Accounts list")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        top_bar = tk.Frame(list_frame)
        top_bar.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(top_bar, text="Search:").pack(side=tk.LEFT, padx=4)
        self.search_var = tk.StringVar()
        ttk.Entry(top_bar, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(top_bar, text="Find", command=self.refresh_accounts).pack(side=tk.LEFT, padx=4)
        ttk.Button(top_bar, text="Refresh", command=lambda: self.refresh_accounts(True)).pack(side=tk.LEFT, padx=4)

        columns = ("id", "name", "balance", "created_at")
        self.accounts_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        for col, text, w in [
            ("id", "ID", 80),
            ("name", "Name", 240),
            ("balance", "Balance", 140),
            ("created_at", "Created at", 200),
        ]:
            self.accounts_tree.heading(col, text=text)
            self.accounts_tree.column(col, width=w, anchor=tk.CENTER)
        self.accounts_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.refresh_accounts(True)

    def create_account(self):
        name = self.acc_name_var.get().strip()
        initial = self.acc_init_var.get().strip()
        try:
            initial_value = float(initial) if initial else 0.0
            acc_id = self.db.create_account(name, initial_value)
            messagebox.showinfo("Success", f"Account created (ID: {acc_id})")
            self.acc_name_var.set("")
            self.acc_init_var.set("0")
            self.refresh_accounts(True)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def refresh_accounts(self, clear_search=False):
        if clear_search:
            self.search_var.set("")
        query = self.search_var.get().strip()
        rows = self.db.search_accounts(query)
        for i in self.accounts_tree.get_children():
            self.accounts_tree.delete(i)
        for r in rows:
            self.accounts_tree.insert("", tk.END, values=r)

    # ---------------- Deposit Tab ----------------
    def _setup_deposit_tab(self):
        frm = self.deposit_tab
        box = ttk.LabelFrame(frm, text="Deposit")
        box.pack(fill=tk.X, padx=8, pady=8)

        self.dep_acc_var = tk.StringVar()
        self.dep_amt_var = tk.StringVar()
        self.dep_note_var = tk.StringVar()

        ttk.Label(box, text="Account ID:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.dep_acc_var, width=12).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(box, text="Amount:").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.dep_amt_var, width=12).grid(row=0, column=3, padx=6, pady=6)
        ttk.Label(box, text="Note:").grid(row=0, column=4, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.dep_note_var, width=30).grid(row=0, column=5, padx=6, pady=6)

        ttk.Button(box, text="Deposit", command=self.do_deposit).grid(row=0, column=6, padx=8, pady=6)

    def do_deposit(self):
        try:
            acc_id = int(self.dep_acc_var.get())
            amt = float(self.dep_amt_var.get())
            note = self.dep_note_var.get()
            new_bal = self.db.deposit(acc_id, amt, note)
            messagebox.showinfo("Success", f"Deposited {amt:.2f}. New balance: {new_bal:.2f}")
            self.dep_amt_var.set("")
            self.dep_note_var.set("")
            self.refresh_accounts(True)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    # ---------------- Withdraw Tab ----------------
    def _setup_withdraw_tab(self):
        frm = self.withdraw_tab
        box = ttk.LabelFrame(frm, text="Withdraw")
        box.pack(fill=tk.X, padx=8, pady=8)

        self.wd_acc_var = tk.StringVar()
        self.wd_amt_var = tk.StringVar()
        self.wd_note_var = tk.StringVar()

        ttk.Label(box, text="Account ID:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.wd_acc_var, width=12).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(box, text="Amount:").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.wd_amt_var, width=12).grid(row=0, column=3, padx=6, pady=6)
        ttk.Label(box, text="Note:").grid(row=0, column=4, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.wd_note_var, width=30).grid(row=0, column=5, padx=6, pady=6)

        ttk.Button(box, text="Withdraw", command=self.do_withdraw).grid(row=0, column=6, padx=8, pady=6)

    def do_withdraw(self):
        try:
            acc_id = int(self.wd_acc_var.get())
            amt = float(self.wd_amt_var.get())
            note = self.wd_note_var.get()
            new_bal = self.db.withdraw(acc_id, amt, note)
            messagebox.showinfo("Success", f"Withdrew {amt:.2f}. New balance: {new_bal:.2f}")
            self.wd_amt_var.set("")
            self.wd_note_var.set("")
            self.refresh_accounts(True)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    # ---------------- Transfer Tab ----------------
    def _setup_transfer_tab(self):
        frm = self.transfer_tab
        box = ttk.LabelFrame(frm, text="Transfer")
        box.pack(fill=tk.X, padx=8, pady=8)

        self.tf_from_var = tk.StringVar()
        self.tf_to_var = tk.StringVar()
        self.tf_amt_var = tk.StringVar()
        self.tf_note_var = tk.StringVar()

        ttk.Label(box, text="From Account ID:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.tf_from_var, width=12).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(box, text="To Account ID:").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.tf_to_var, width=12).grid(row=0, column=3, padx=6, pady=6)
        ttk.Label(box, text="Amount:").grid(row=0, column=4, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.tf_amt_var, width=12).grid(row=0, column=5, padx=6, pady=6)
        ttk.Label(box, text="Note:").grid(row=0, column=6, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.tf_note_var, width=24).grid(row=0, column=7, padx=6, pady=6)

        ttk.Button(box, text="Transfer", command=self.do_transfer).grid(row=0, column=8, padx=8, pady=6)

    def do_transfer(self):
        try:
            from_id = int(self.tf_from_var.get())
            to_id = int(self.tf_to_var.get())
            amt = float(self.tf_amt_var.get())
            note = self.tf_note_var.get()
            new_from, new_to = self.db.transfer(from_id, to_id, amt, note)
            messagebox.showinfo("Success", f"Transferred {amt:.2f}. From new balance: {new_from:.2f}, To new balance: {new_to:.2f}")
            self.tf_amt_var.set("")
            self.tf_note_var.set("")
            self.refresh_accounts(True)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    # ---------------- Transactions Tab ----------------
    def _setup_transactions_tab(self):
        frm = self.transactions_tab
        box = ttk.LabelFrame(frm, text="Transaction history")
        box.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        top = tk.Frame(box)
        top.pack(fill=tk.X, padx=6, pady=6)

        self.tx_acc_var = tk.StringVar()
        self.tx_limit_var = tk.StringVar(value="50")

        ttk.Label(top, text="Account ID:").pack(side=tk.LEFT, padx=4)
        ttk.Entry(top, textvariable=self.tx_acc_var, width=12).pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="Limit:").pack(side=tk.LEFT, padx=4)
        ttk.Entry(top, textvariable=self.tx_limit_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Load", command=self.load_transactions).pack(side=tk.LEFT, padx=6)

        columns = ("id", "type", "amount", "timestamp", "note", "related")
        self.tx_tree = ttk.Treeview(box, columns=columns, show="headings", height=16)
        headings = [
            ("id", "ID", 80),
            ("type", "Type", 120),
            ("amount", "Amount", 120),
            ("timestamp", "Timestamp", 180),
            ("note", "Note", 240),
            ("related", "Related Acc", 120),
        ]
        for col, text, w in headings:
            self.tx_tree.heading(col, text=text)
            self.tx_tree.column(col, width=w, anchor=tk.CENTER)
        self.tx_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def load_transactions(self):
        try:
            acc_id = int(self.tx_acc_var.get())
            limit = int(self.tx_limit_var.get())
            rows = self.db.list_transactions(acc_id, limit)
            for i in self.tx_tree.get_children():
                self.tx_tree.delete(i)
            for r in rows:
                self.tx_tree.insert("", tk.END, values=r)
        except ValueError:
            messagebox.showerror("Error", "Please enter valid Account ID and Limit.")

    # ---------------- Admin Tab ----------------
    def _setup_admin_tab(self):
        frm = self.admin_tab
        box = ttk.LabelFrame(frm, text="Admin operations")
        box.pack(fill=tk.X, padx=8, pady=8)

        self.del_acc_var = tk.StringVar()

        ttk.Label(box, text="Delete Account ID:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Entry(box, textvariable=self.del_acc_var, width=12).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(box, text="Delete", command=self.delete_account).grid(row=0, column=2, padx=8, pady=6)

        # Quick balances checker
        bal_box = ttk.LabelFrame(frm, text="Quick balance check")
        bal_box.pack(fill=tk.X, padx=8, pady=8)
        self.bal_acc_var = tk.StringVar()
        ttk.Label(bal_box, text="Account ID:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Entry(bal_box, textvariable=self.bal_acc_var, width=12).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(bal_box, text="Check", command=self.check_balance).grid(row=0, column=2, padx=8, pady=6)

    def delete_account(self):
        try:
            acc_id = int(self.del_acc_var.get())
            # Confirm
            if messagebox.askyesno("Confirm", f"Delete account {acc_id}? (Requires zero balance)"):
                self.db.delete_account(acc_id)
                messagebox.showinfo("Deleted", f"Account {acc_id} deleted.")
                self.del_acc_var.set("")
                self.refresh_accounts(True)
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def check_balance(self):
        try:
            acc_id = int(self.bal_acc_var.get())
            acc = self.db.get_account(acc_id)
            if not acc:
                messagebox.showerror("Not found", "Account not found.")
                return
            messagebox.showinfo("Balance", f"Account {acc[0]} ({acc[1]}) balance: {acc[2]:.2f}")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid Account ID.")


# --------------------------
# Run app
# --------------------------
if __name__ == "__main__":
    app = BankApp()
    app.mainloop()
