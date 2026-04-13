
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, g
)
from functools import wraps
import pymysql
import pymysql.cursors
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────
def _new_connection():
    return pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        port=Config.DB_PORT,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

# ──────────────────────────────────────────────
# Auto-initialize database tables on startup
# ──────────────────────────────────────────────
def init_db():
    schema_sql = """
CREATE TABLE IF NOT EXISTS DEALERSHIP (
    Dealership_ID INT AUTO_INCREMENT PRIMARY KEY,
    Name          VARCHAR(150) NOT NULL,
    Location      VARCHAR(255) NOT NULL,
    Contact       VARCHAR(50)  NOT NULL
);

CREATE TABLE IF NOT EXISTS USER (
    User_ID        INT AUTO_INCREMENT PRIMARY KEY,
    Name           VARCHAR(150) NOT NULL,
    Email          VARCHAR(255) NOT NULL UNIQUE,
    Password       VARCHAR(255) NOT NULL,
    Role           ENUM('salesperson', 'factory_worker', 'manager') NOT NULL,
    Dealership_ID  INT NULL,
    CONSTRAINT fk_user_dealership FOREIGN KEY (Dealership_ID)
        REFERENCES DEALERSHIP(Dealership_ID)
        ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS CUSTOMER (
    Customer_ID   INT AUTO_INCREMENT PRIMARY KEY,
    Name          VARCHAR(150) NOT NULL,
    Phone         VARCHAR(20)  NOT NULL,
    Email         VARCHAR(255) NOT NULL UNIQUE,
    Address       VARCHAR(255) NOT NULL,
    Dealership_ID INT NOT NULL,
    CONSTRAINT fk_customer_dealership FOREIGN KEY (Dealership_ID)
        REFERENCES DEALERSHIP(Dealership_ID)
        ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS MODEL (
    Model_ID      INT AUTO_INCREMENT PRIMARY KEY,
    Model_Name    VARCHAR(150) NOT NULL,
    Manufacturer  VARCHAR(150) NOT NULL,
    Launch_Year   YEAR         NOT NULL
);

CREATE TABLE IF NOT EXISTS VARIANT (
    Variant_ID    INT AUTO_INCREMENT PRIMARY KEY,
    Model_ID      INT            NOT NULL,
    Variant_Name  VARCHAR(150)   NOT NULL,
    Engine_Type   VARCHAR(100)   NOT NULL,
    Fuel_Type     VARCHAR(50)    NOT NULL,
    Transmission  VARCHAR(50)    NOT NULL,
    Cost          DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_variant_model FOREIGN KEY (Model_ID)
        REFERENCES MODEL(Model_ID)
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS PART (
    Part_ID     INT AUTO_INCREMENT PRIMARY KEY,
    Part_Name   VARCHAR(150) NOT NULL,
    Description TEXT
);

CREATE TABLE IF NOT EXISTS VARIANT_PART (
    Variant_ID        INT NOT NULL,
    Part_ID           INT NOT NULL,
    Required_Quantity INT NOT NULL DEFAULT 1,
    PRIMARY KEY (Variant_ID, Part_ID),
    CONSTRAINT fk_vp_variant FOREIGN KEY (Variant_ID)
        REFERENCES VARIANT(Variant_ID) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_vp_part FOREIGN KEY (Part_ID)
        REFERENCES PART(Part_ID) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS ORDER_TABLE (
    Order_ID       INT AUTO_INCREMENT PRIMARY KEY,
    Customer_ID    INT NOT NULL,
    Variant_ID     INT NOT NULL,
    Salesperson_ID INT NOT NULL,
    Order_Date     DATE NOT NULL,
    Status         ENUM('pending','accepted','in_production','completed','delivered') NOT NULL DEFAULT 'pending',
    CONSTRAINT fk_order_customer    FOREIGN KEY (Customer_ID)    REFERENCES CUSTOMER(Customer_ID) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_order_variant     FOREIGN KEY (Variant_ID)     REFERENCES VARIANT(Variant_ID)   ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_order_salesperson FOREIGN KEY (Salesperson_ID) REFERENCES USER(User_ID)         ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS CAR_PRODUCTION (
    Car_ID                INT AUTO_INCREMENT PRIMARY KEY,
    Order_ID              INT  NOT NULL,
    Variant_ID            INT  NOT NULL,
    Production_Start_Date DATE NOT NULL,
    Status                ENUM('in_production','completed') NOT NULL DEFAULT 'in_production',
    CONSTRAINT fk_cp_order   FOREIGN KEY (Order_ID)   REFERENCES ORDER_TABLE(Order_ID) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_cp_variant FOREIGN KEY (Variant_ID) REFERENCES VARIANT(Variant_ID)   ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS PRODUCTION_SECTION (
    Section_ID   INT AUTO_INCREMENT PRIMARY KEY,
    Section_Name VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS SECTION_PROGRESS (
    Progress_ID       INT AUTO_INCREMENT PRIMARY KEY,
    Car_ID            INT  NOT NULL,
    Section_ID        INT  NOT NULL,
    Worker_ID         INT  NOT NULL,
    Completion_Status ENUM('pending','completed','failed') NOT NULL DEFAULT 'pending',
    Completion_Date   DATE NULL,
    CONSTRAINT fk_sp_car     FOREIGN KEY (Car_ID)     REFERENCES CAR_PRODUCTION(Car_ID)         ON DELETE CASCADE  ON UPDATE CASCADE,
    CONSTRAINT fk_sp_section FOREIGN KEY (Section_ID) REFERENCES PRODUCTION_SECTION(Section_ID) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_sp_worker  FOREIGN KEY (Worker_ID)  REFERENCES USER(User_ID)                  ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS ISSUE_LOG (
    Issue_ID    INT AUTO_INCREMENT PRIMARY KEY,
    Car_ID      INT NOT NULL,
    Reporter_ID INT NOT NULL,
    Description TEXT NOT NULL,
    Status      ENUM('open','resolved') NOT NULL DEFAULT 'open',
    Created_At  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Resolved_At TIMESTAMP NULL,
    CONSTRAINT fk_il_car      FOREIGN KEY (Car_ID)      REFERENCES CAR_PRODUCTION(Car_ID) ON DELETE CASCADE  ON UPDATE CASCADE,
    CONSTRAINT fk_il_reporter FOREIGN KEY (Reporter_ID) REFERENCES USER(User_ID)          ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS PRODUCED_CAR (
    Produced_Car_ID INT AUTO_INCREMENT PRIMARY KEY,
    Car_ID          INT  NOT NULL UNIQUE,
    Completion_Date DATE NOT NULL,
    Quality_Status  ENUM('passed','failed') NOT NULL,
    CONSTRAINT fk_pc_car FOREIGN KEY (Car_ID) REFERENCES CAR_PRODUCTION(Car_ID) ON DELETE RESTRICT ON UPDATE CASCADE
);
"""
    try:
        conn = _new_connection()
        conn.autocommit = True
        cur = conn.cursor()
        for statement in schema_sql.strip().split(';'):
            s = statement.strip()
            if s:
                cur.execute(s)
        # Seed production sections if empty
        cur.execute("SELECT COUNT(*) as cnt FROM PRODUCTION_SECTION")
        if cur.fetchone()['cnt'] == 0:
            sections = ['Body Shop','Paint Shop','Engine Assembly','Trim and Chassis','Final Assembly','Quality Inspection']
            for sec in sections:
                cur.execute("INSERT INTO PRODUCTION_SECTION (Section_Name) VALUES (%s)", (sec,))
        cur.close()
        conn.close()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"⚠️ DB init warning: {e}")

with app.app_context():
    init_db()

def get_db():
    if "db" not in g:
        g.db = _new_connection()
    else:
        # Reconnect if the server closed the connection
        try:
            g.db.ping(reconnect=True)
        except pymysql.Error:
            g.db = _new_connection()
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query_db(sql, args=(), one=False):
    cur = get_db().cursor()
    try:
        cur.execute(sql, args)
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv
    finally:
        cur.close()

def execute_db(sql, args=()):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    except pymysql.Error:
        conn.rollback()
        raise
    finally:
        cur.close()


# ──────────────────────────────────────────────
# Auth decorators
# ──────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if session.get("role") not in allowed_roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ──────────────────────────────────────────────
# Root
# ──────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("role")
    if role == "salesperson":
        return redirect(url_for("salesperson_dashboard"))
    if role == "factory_worker":
        return redirect(url_for("factory_dashboard"))
    if role == "manager":
        return redirect(url_for("manager_dashboard"))
    return redirect(url_for("login"))


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = query_db(
            "SELECT * FROM USER WHERE Email = %s AND Password = %s",
            (email, password),
            one=True,
        )
        if user:
            session["user_id"]       = user["User_ID"]
            session["user_name"]     = user["Name"]
            session["role"]          = user["Role"]
            session["dealership_id"] = user.get("Dealership_ID")
            
            flash(f"Welcome back, {user['Name']}!", "success")
            
            # Redirect explicitly based on role
            if user["Role"] == "salesperson":
                return redirect(url_for("salesperson_dashboard"))
            elif user["Role"] == "factory_worker":
                return redirect(url_for("factory_dashboard"))
            elif user["Role"] == "manager":
                return redirect(url_for("manager_dashboard"))
            else:
                return redirect(url_for("index"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ──────────────────────────────────────────────
# Salesperson routes
# ──────────────────────────────────────────────
@app.route("/salesperson/dashboard")
@role_required("salesperson", "manager")
def salesperson_dashboard():
    user_id = session["user_id"]
    is_manager = session.get("role") == "manager"

    if is_manager:
        total_orders = query_db("SELECT COUNT(*) AS cnt FROM ORDER_TABLE", one=True)["cnt"]
        pending = query_db("SELECT COUNT(*) AS cnt FROM ORDER_TABLE WHERE Status = 'pending'", one=True)["cnt"]
        delivered = query_db("SELECT COUNT(*) AS cnt FROM ORDER_TABLE WHERE Status = 'delivered'", one=True)["cnt"]
        recent_orders = query_db(
            """
            SELECT o.Order_ID, c.Name AS customer_name,
                   v.Variant_Name, o.Order_Date, o.Status
            FROM ORDER_TABLE o
            JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
            JOIN VARIANT  v ON o.Variant_ID  = v.Variant_ID
            ORDER BY o.Order_Date DESC
            LIMIT 5
            """
        )
    else:
        total_orders = query_db(
            "SELECT COUNT(*) AS cnt FROM ORDER_TABLE WHERE Salesperson_ID = %s",
            (user_id,), one=True
        )["cnt"]
        pending = query_db(
            "SELECT COUNT(*) AS cnt FROM ORDER_TABLE WHERE Salesperson_ID = %s AND Status = 'pending'",
            (user_id,), one=True
        )["cnt"]
        delivered = query_db(
            "SELECT COUNT(*) AS cnt FROM ORDER_TABLE WHERE Salesperson_ID = %s AND Status = 'delivered'",
            (user_id,), one=True
        )["cnt"]
        recent_orders = query_db(
            """
            SELECT o.Order_ID, c.Name AS customer_name,
                   v.Variant_Name, o.Order_Date, o.Status
            FROM ORDER_TABLE o
            JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
            JOIN VARIANT  v ON o.Variant_ID  = v.Variant_ID
            WHERE o.Salesperson_ID = %s
            ORDER BY o.Order_Date DESC
            LIMIT 5
            """,
            (user_id,)
        )

    return render_template(
        "salesperson/dashboard.html",
        total_orders=total_orders,
        pending=pending,
        delivered=delivered,
        recent_orders=recent_orders,
    )


@app.route("/salesperson/orders")
@role_required("salesperson", "manager")
def salesperson_orders():
    user_id = session["user_id"]
    is_manager = session.get("role") == "manager"
    status_filter = request.args.get("status", "")

    query = """
        SELECT o.Order_ID, c.Name AS customer_name,
               m.Model_Name, v.Variant_Name, o.Order_Date, o.Status,
               CASE
                 WHEN o.Status IN ('completed', 'delivered') THEN 'Production Complete'
                 WHEN cp.Status = 'completed' THEN 'Production Complete'
                 ELSE COALESCE(
                   (SELECT ps.Section_Name
                    FROM SECTION_PROGRESS sp
                    JOIN PRODUCTION_SECTION ps ON sp.Section_ID = ps.Section_ID
                    WHERE sp.Car_ID = cp.Car_ID AND sp.Completion_Status = 'pending'
                    ORDER BY sp.Section_ID ASC LIMIT 1),
                   'Not Started'
                 )
               END AS Production_Status
        FROM ORDER_TABLE o
        JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
        JOIN VARIANT  v ON o.Variant_ID  = v.Variant_ID
        JOIN MODEL    m ON v.Model_ID    = m.Model_ID
        LEFT JOIN CAR_PRODUCTION cp ON o.Order_ID = cp.Order_ID
        WHERE 1=1
    """

    args = []
    if not is_manager:
        query += " AND o.Salesperson_ID = %s"
        args.append(user_id)
    if status_filter:
        query += " AND o.Status = %s"
        args.append(status_filter)

    query += " ORDER BY o.Order_Date DESC"

    orders = query_db(query, tuple(args))
    return render_template("salesperson/track_orders.html", orders=orders, current_status=status_filter)


@app.route("/salesperson/new-order", methods=["GET", "POST"])
@role_required("salesperson", "manager")
def salesperson_new_order():
    user_id      = session["user_id"]
    dealership_id = session.get("dealership_id")

    customers = query_db(
        "SELECT Customer_ID, Name FROM CUSTOMER WHERE Dealership_ID = %s",
        (dealership_id,)
    )
    models = query_db("SELECT Model_ID, Model_Name FROM MODEL ORDER BY Model_Name")
    
    variants = query_db(
        """
        SELECT Variant_ID, Model_ID, Variant_Name, Cost
        FROM VARIANT
        ORDER BY Variant_Name
        """
    )

    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        variant_id  = request.form.get("variant_id")
        order_date  = request.form.get("order_date")

        if not all([customer_id, variant_id, order_date]):
            flash("All fields are required.", "danger")
        else:
            execute_db(
                """
                INSERT INTO ORDER_TABLE (Customer_ID, Variant_ID, Salesperson_ID, Order_Date, Status)
                VALUES (%s, %s, %s, %s, 'pending')
                """,
                (customer_id, variant_id, user_id, order_date)
            )
            flash("Order placed successfully!", "success")
            return redirect(url_for("salesperson_orders"))

    return render_template(
        "salesperson/new_order.html",
        customers=customers,
        models=models,
        variants=variants,
    )


@app.route("/salesperson/customers", methods=["GET", "POST"])
@role_required("salesperson", "manager")
def salesperson_customers():
    dealership_id = session.get("dealership_id")
    is_manager = session.get("role") == "manager"

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        address = request.form.get("address")
        post_dealership = request.form.get("dealership_id") if is_manager else dealership_id

        if all([name, phone, email, address, post_dealership]):
            try:
                execute_db(
                    """
                    INSERT INTO CUSTOMER (Name, Phone, Email, Address, Dealership_ID)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (name, phone, email, address, post_dealership)
                )
                flash("New customer added successfully!", "success")
            except pymysql.Error as err:
                flash(f"Error adding customer: {err}", "danger")
        else:
            flash("All fields are required.", "danger")
        return redirect(url_for("salesperson_customers"))

    if is_manager:
        customers = query_db(
            """
            SELECT c.Customer_ID, c.Name, c.Phone, c.Email, c.Address,
                   COUNT(o.Order_ID) AS order_count
            FROM CUSTOMER c
            LEFT JOIN ORDER_TABLE o ON c.Customer_ID = o.Customer_ID
            GROUP BY c.Customer_ID
            ORDER BY c.Name
            """
        )
    else:
        customers = query_db(
            """
            SELECT c.Customer_ID, c.Name, c.Phone, c.Email, c.Address,
                   COUNT(o.Order_ID) AS order_count
            FROM CUSTOMER c
            LEFT JOIN ORDER_TABLE o ON c.Customer_ID = o.Customer_ID
            WHERE c.Dealership_ID = %s
            GROUP BY c.Customer_ID
            ORDER BY c.Name
            """,
            (dealership_id,)
        )

    dealerships = query_db("SELECT Dealership_ID, Name FROM DEALERSHIP ORDER BY Name") if is_manager else []
    return render_template("salesperson/customers.html", customers=customers, dealerships=dealerships, is_manager=is_manager)


@app.route("/salesperson/variants")
@role_required("salesperson", "manager")
def salesperson_variants():
    variants = query_db(
        """
        SELECT v.Variant_ID, m.Model_Name, m.Manufacturer, m.Launch_Year,
               v.Variant_Name, v.Engine_Type, v.Fuel_Type, v.Transmission, v.Cost
        FROM VARIANT v
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        ORDER BY m.Model_Name, v.Variant_Name
        """
    )
    return render_template("salesperson/variants.html", variants=variants)


# ──────────────────────────────────────────────
# Factory Worker routes
# ──────────────────────────────────────────────
@app.route("/factory/dashboard")
@role_required("factory_worker", "manager")
def factory_dashboard():
    worker_id = session["user_id"]

    section_info = query_db(
        """
        SELECT ps.Section_Name 
        FROM SECTION_PROGRESS sp
        JOIN PRODUCTION_SECTION ps ON sp.Section_ID = ps.Section_ID
        WHERE sp.Worker_ID = %s LIMIT 1
        """, (worker_id,), one=True
    )
    section_name = section_info["Section_Name"] if section_info else "Unassigned Section"

    pending_tasks = query_db(
        """
        SELECT sp.Progress_ID, cp.Car_ID, cp.Order_ID, 
               m.Model_Name, v.Variant_Name, cp.Production_Start_Date
        FROM SECTION_PROGRESS sp
        JOIN CAR_PRODUCTION cp ON sp.Car_ID = cp.Car_ID
        JOIN VARIANT v ON cp.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        WHERE sp.Worker_ID = %s AND sp.Completion_Status = 'pending'
        ORDER BY cp.Production_Start_Date ASC
        """, (worker_id,)
    )

    completed_tasks = query_db(
        """
        SELECT cp.Car_ID, m.Model_Name, v.Variant_Name, sp.Completion_Date
        FROM SECTION_PROGRESS sp
        JOIN CAR_PRODUCTION cp ON sp.Car_ID = cp.Car_ID
        JOIN VARIANT v ON cp.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        WHERE sp.Worker_ID = %s AND sp.Completion_Status = 'completed'
        ORDER BY sp.Completion_Date DESC
        """, (worker_id,)
    )

    return render_template(
        "factory_worker/dashboard.html",
        section_name=section_name,
        pending_tasks=pending_tasks,
        completed_tasks=completed_tasks,
    )


@app.route("/factory/complete-section", methods=["POST"])
@role_required("factory_worker", "manager")
def factory_complete_section():
    worker_id = session["user_id"]
    progress_id = request.form.get("progress_id")
    
    if progress_id:
        execute_db(
            """
            UPDATE SECTION_PROGRESS 
            SET Completion_Status = 'completed', Completion_Date = CURDATE()
            WHERE Progress_ID = %s AND Worker_ID = %s
            """, (progress_id, worker_id)
        )
        
        prog = query_db("SELECT Car_ID FROM SECTION_PROGRESS WHERE Progress_ID = %s", (progress_id,), one=True)
        if prog:
            car_id = prog["Car_ID"]
            pending = query_db(
                "SELECT COUNT(*) AS cnt FROM SECTION_PROGRESS WHERE Car_ID = %s AND Completion_Status != 'completed'",
                (car_id,), one=True
            )["cnt"]
            
            if pending == 0:
                issues = query_db(
                    "SELECT COUNT(*) AS cnt FROM ISSUE_LOG WHERE Car_ID = %s AND Status = 'open'",
                    (car_id,), one=True
                )["cnt"]

                if issues > 0:
                    flash(f"Section complete! However, Car #{car_id} is held in QC due to {issues} open issue(s).", "warning")
                else:
                    execute_db(
                        "INSERT INTO PRODUCED_CAR (Car_ID, Completion_Date, Quality_Status) VALUES (%s, CURDATE(), 'passed') "
                        "ON DUPLICATE KEY UPDATE Completion_Date=CURDATE()", (car_id,)
                    )
                    execute_db("UPDATE CAR_PRODUCTION SET Status = 'completed' WHERE Car_ID = %s", (car_id,))
                    
                    cp = query_db("SELECT Order_ID FROM CAR_PRODUCTION WHERE Car_ID = %s", (car_id,), one=True)
                    if cp:
                        execute_db("UPDATE ORDER_TABLE SET Status = 'completed' WHERE Order_ID = %s", (cp["Order_ID"],))
                    
                    flash("Section complete! The car has successfully finished all production phases.", "success")
            else:
                flash("Section marked as complete.", "success")

    return redirect(url_for("factory_dashboard"))


# ──────────────────────────────────────────────
# Quality Control routes
# ──────────────────────────────────────────────
@app.route("/qc")
def qc_dashboard():
    role = session.get("role")
    if role not in ["manager", "factory_worker"]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("login"))

    open_issues = query_db(
        """
        SELECT i.Issue_ID, i.Car_ID, i.Description, i.Created_At,
               u.Name AS Reporter_Name, m.Model_Name, v.Variant_Name
        FROM ISSUE_LOG i
        JOIN CAR_PRODUCTION cp ON i.Car_ID = cp.Car_ID
        JOIN VARIANT v ON cp.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        JOIN USER u ON i.Reporter_ID = u.User_ID
        WHERE i.Status = 'open'
        ORDER BY i.Created_At DESC
        """
    )
    
    resolved_issues = query_db(
        """
        SELECT i.Issue_ID, i.Car_ID, i.Description, i.Resolved_At,
               u.Name AS Reporter_Name, m.Model_Name, v.Variant_Name
        FROM ISSUE_LOG i
        JOIN CAR_PRODUCTION cp ON i.Car_ID = cp.Car_ID
        JOIN VARIANT v ON cp.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        JOIN USER u ON i.Reporter_ID = u.User_ID
        WHERE i.Status = 'resolved'
        ORDER BY i.Resolved_At DESC
        """
    )

    return render_template("qc/dashboard.html", open_issues=open_issues, resolved_issues=resolved_issues)


@app.route("/qc/raise", methods=["POST"])
def qc_raise():
    role = session.get("role")
    if role not in ["manager", "factory_worker"]:
        return redirect(url_for("login"))
        
    car_id = request.form.get("car_id")
    description = request.form.get("description")
    reporter_id = session.get("user_id")
    
    if car_id and description:
        execute_db(
            "INSERT INTO ISSUE_LOG (Car_ID, Reporter_ID, Description, Status) VALUES (%s, %s, %s, 'open')",
            (car_id, reporter_id, description)
        )
        flash(f"QC Issue logged for Car #{car_id}.", "danger")
        
    return redirect(request.referrer or url_for("qc_dashboard"))


@app.route("/qc/resolve", methods=["POST"])
def qc_resolve():
    role = session.get("role")
    if role not in ["manager", "factory_worker"]:
        return redirect(url_for("login"))
        
    issue_id = request.form.get("issue_id")
    
    if issue_id:
        execute_db(
            "UPDATE ISSUE_LOG SET Status = 'resolved', Resolved_At = CURRENT_TIMESTAMP WHERE Issue_ID = %s",
            (issue_id,)
        )
        
        i = query_db("SELECT Car_ID FROM ISSUE_LOG WHERE Issue_ID = %s", (issue_id,), one=True)
        if i:
            car_id = i["Car_ID"]
            pending_sections = query_db(
                "SELECT COUNT(*) AS cnt FROM SECTION_PROGRESS WHERE Car_ID = %s AND Completion_Status != 'completed'",
                (car_id,), one=True
            )["cnt"]
            open_issues = query_db(
                "SELECT COUNT(*) AS cnt FROM ISSUE_LOG WHERE Car_ID = %s AND Status = 'open'",
                (car_id,), one=True
            )["cnt"]
            
            if pending_sections == 0 and open_issues == 0:
                execute_db(
                    "INSERT INTO PRODUCED_CAR (Car_ID, Completion_Date, Quality_Status) VALUES (%s, CURDATE(), 'passed') "
                    "ON DUPLICATE KEY UPDATE Completion_Date=CURDATE()", (car_id,)
                )
                execute_db("UPDATE CAR_PRODUCTION SET Status = 'completed' WHERE Car_ID = %s", (car_id,))
                
                cp = query_db("SELECT Order_ID FROM CAR_PRODUCTION WHERE Car_ID = %s", (car_id,), one=True)
                if cp:
                    execute_db("UPDATE ORDER_TABLE SET Status = 'completed' WHERE Order_ID = %s", (cp["Order_ID"],))
                
                flash(f"Issue #{issue_id} resolved! Car #{car_id} was fully built and has now been released to Completed Cars.", "success")
            else:
                flash(f"Issue #{issue_id} resolved successfully.", "success")

    return redirect(url_for("qc_dashboard"))


# ──────────────────────────────────────────────
# Manager routes
# ──────────────────────────────────────────────
@app.route("/manager/dashboard")
@role_required("manager")
def manager_dashboard():
    # 1. Overview Stats
    total_orders = query_db("SELECT COUNT(*) AS cnt FROM ORDER_TABLE", one=True)["cnt"]
    in_prod      = query_db("SELECT COUNT(*) AS cnt FROM CAR_PRODUCTION WHERE Status = 'in_production'", one=True)["cnt"]
    completed    = query_db("SELECT COUNT(*) AS cnt FROM PRODUCED_CAR", one=True)["cnt"]
    total_dealerships = query_db("SELECT COUNT(*) AS cnt FROM DEALERSHIP", one=True)["cnt"]

    # 2. Charts
    orders_per_dealership = query_db(
        """
        SELECT d.Name AS label, COUNT(o.Order_ID) AS count
        FROM DEALERSHIP d
        LEFT JOIN CUSTOMER c ON d.Dealership_ID = c.Dealership_ID
        LEFT JOIN ORDER_TABLE o ON c.Customer_ID = o.Customer_ID
        GROUP BY d.Dealership_ID
        ORDER BY count DESC
        """
    )
    order_status_dist = query_db("SELECT Status AS label, COUNT(*) AS count FROM ORDER_TABLE GROUP BY Status")

    # 3. All Orders
    dealership_id_filter = request.args.get("dealership_id", "")
    status_filter = request.args.get("status", "")

    query = """
        SELECT o.Order_ID, c.Name AS customer_name, d.Name AS dealership_name,
               m.Model_Name, v.Variant_Name, o.Order_Date, o.Status
        FROM ORDER_TABLE o
        JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
        JOIN DEALERSHIP d ON c.Dealership_ID = d.Dealership_ID
        JOIN VARIANT v ON o.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        WHERE 1=1
    """
    args = []
    if dealership_id_filter:
        query += " AND d.Dealership_ID = %s"
        args.append(dealership_id_filter)
    if status_filter:
        query += " AND o.Status = %s"
        args.append(status_filter)
    query += " ORDER BY o.Order_Date DESC"
    all_orders = query_db(query, tuple(args))
    dealerships = query_db("SELECT Dealership_ID, Name FROM DEALERSHIP ORDER BY Name")

    # 4. Production Status
    production_cars = query_db(
        """
        SELECT cp.Car_ID, cp.Order_ID, m.Model_Name, v.Variant_Name, cp.Production_Start_Date,
               (SELECT COUNT(*) FROM SECTION_PROGRESS sp WHERE sp.Car_ID = cp.Car_ID AND sp.Completion_Status = 'completed') AS sections_completed,
               COALESCE(
                 (SELECT ps.Section_Name 
                  FROM SECTION_PROGRESS sp2 
                  JOIN PRODUCTION_SECTION ps ON sp2.Section_ID = ps.Section_ID 
                  WHERE sp2.Car_ID = cp.Car_ID AND sp2.Completion_Status = 'pending' 
                  ORDER BY sp2.Section_ID ASC LIMIT 1), 
                 'Completed'
               ) AS Current_Section
        FROM CAR_PRODUCTION cp
        JOIN VARIANT v ON cp.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        WHERE cp.Status = 'in_production'
        ORDER BY cp.Production_Start_Date ASC
        """
    )

    # 5. Completed Cars
    completed_cars = query_db(
        """
        SELECT pc.Produced_Car_ID, pc.Car_ID, m.Model_Name, v.Variant_Name, 
               d.Name AS dealership_name, pc.Completion_Date, pc.Quality_Status
        FROM PRODUCED_CAR pc
        JOIN CAR_PRODUCTION cp ON pc.Car_ID = cp.Car_ID
        JOIN ORDER_TABLE o ON cp.Order_ID = o.Order_ID
        JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
        JOIN DEALERSHIP d ON c.Dealership_ID = d.Dealership_ID
        JOIN VARIANT v ON cp.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        ORDER BY pc.Completion_Date DESC
        """
    )

    # 6. Recent Complaints
    complaints = query_db("""
        SELECT c.Complaint_ID, c.Order_ID, c.Priority, c.Status, c.Created_At, cust.Name AS customer_name
        FROM COMPLAINTS c
        JOIN CUSTOMER cust ON c.Customer_ID = cust.Customer_ID
        ORDER BY c.Created_At DESC
        LIMIT 5
    """)

    return render_template(
        "manager/dashboard.html",
        total_orders=total_orders,
        in_prod=in_prod,
        completed=completed,
        total_dealerships=total_dealerships,
        orders_per_dealership=orders_per_dealership,
        order_status_dist=order_status_dist,
        all_orders=all_orders,
        dealerships=dealerships,
        current_dealership=dealership_id_filter,
        current_status=status_filter,
        production_cars=production_cars,
        completed_cars=completed_cars,
        complaints=complaints
    )


@app.route("/manager/accept-order", methods=["POST"])
@role_required("manager")
def manager_accept_order():
    order_id = request.form.get("order_id")
    if not order_id:
        return redirect(url_for("manager_dashboard"))

    o = query_db("SELECT Variant_ID, Status FROM ORDER_TABLE WHERE Order_ID = %s", (order_id,), one=True)
    if not o or o["Status"] != 'pending':
        flash("Order cannot be accepted. It might have already been processed.", "warning")
        return redirect(url_for("manager_dashboard"))
        
    # Start production immediately
    car_id = execute_db(
        "INSERT INTO CAR_PRODUCTION (Order_ID, Variant_ID, Production_Start_Date, Status) VALUES (%s, %s, CURDATE(), 'in_production')",
        (order_id, o["Variant_ID"])
    )
    
    # Assign sections to available workers uniformly to distribute load
    workers = query_db("SELECT User_ID FROM USER WHERE Role = 'factory_worker' LIMIT 6")
    worker_ids = [w["User_ID"] for w in workers]
    if not worker_ids:
        worker_ids = [session["user_id"]]
        
    for section_id in range(1, 7):
        w_id = worker_ids[section_id % len(worker_ids)]
        execute_db(
            "INSERT INTO SECTION_PROGRESS (Car_ID, Section_ID, Worker_ID, Completion_Status) VALUES (%s, %s, %s, 'pending')",
            (car_id, section_id, w_id)
        )
        
    # Order is now in production
    execute_db("UPDATE ORDER_TABLE SET Status = 'in_production' WHERE Order_ID = %s", (order_id,))
    
    flash(f"Order #{order_id} explicitly accepted! Pipeline generated for Car #{car_id}.", "success")
    return redirect(url_for("manager_dashboard"))


# ──────────────────────────────────────────────
# Manager Employee Management routes
# ──────────────────────────────────────────────
@app.route("/manager/employees")
@role_required("manager")
def manager_employees():
    """View all employees with their details and performance metrics"""
    role_filter = request.args.get("role", "")
    
    query = """
        SELECT u.User_ID, u.Name, u.Email, u.Role, u.Dealership_ID, d.Name AS Dealership_Name,
               CASE 
                   WHEN u.Role = 'salesperson' THEN 
                       (SELECT COUNT(*) FROM ORDER_TABLE WHERE Salesperson_ID = u.User_ID)
                   WHEN u.Role = 'factory_worker' THEN 
                       (SELECT COUNT(*) FROM SECTION_PROGRESS WHERE Worker_ID = u.User_ID)
                   ELSE 0
               END AS task_count
        FROM USER u
        LEFT JOIN DEALERSHIP d ON u.Dealership_ID = d.Dealership_ID
        WHERE u.Role IN ('salesperson', 'factory_worker')
    """
    
    args = []
    if role_filter:
        query += " AND u.Role = %s"
        args.append(role_filter)
    
    query += " ORDER BY u.Role, u.Name"
    employees = query_db(query, tuple(args))
    
    return render_template(
        "manager/employees.html",
        employees=employees,
        current_role_filter=role_filter
    )


@app.route("/manager/employee/<int:employee_id>")
@role_required("manager")
def manager_employee_detail(employee_id):
    """View detailed profile and performance metrics for a specific employee"""
    employee = query_db(
        """
        SELECT u.User_ID, u.Name, u.Email, u.Role, u.Dealership_ID, d.Name AS Dealership_Name
        FROM USER u
        LEFT JOIN DEALERSHIP d ON u.Dealership_ID = d.Dealership_ID
        WHERE u.User_ID = %s AND u.Role IN ('salesperson', 'factory_worker')
        """,
        (employee_id,),
        one=True
    )
    
    if not employee:
        flash("Employee not found.", "danger")
        return redirect(url_for("manager_employees"))
    
    # Get role-specific details
    if employee["Role"] == "salesperson":
        # Salesperson performance metrics
        performance = query_db(
            """
            SELECT 
                COUNT(o.Order_ID) AS total_orders,
                SUM(CASE WHEN o.Status = 'completed' THEN 1 ELSE 0 END) AS completed_orders,
                SUM(CASE WHEN o.Status = 'in_production' THEN 1 ELSE 0 END) AS in_production,
                SUM(CASE WHEN o.Status = 'pending' THEN 1 ELSE 0 END) AS pending_orders,
                SUM(CASE WHEN o.Status = 'delivered' THEN 1 ELSE 0 END) AS delivered_orders,
                MAX(o.Order_Date) AS last_order_date
            FROM ORDER_TABLE o
            WHERE o.Salesperson_ID = %s
            """,
            (employee_id,),
            one=True
        )
        
        recent_orders = query_db(
            """
            SELECT o.Order_ID, c.Name AS customer_name, v.Variant_Name, 
                   o.Order_Date, o.Status
            FROM ORDER_TABLE o
            JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
            JOIN VARIANT v ON o.Variant_ID = v.Variant_ID
            WHERE o.Salesperson_ID = %s
            ORDER BY o.Order_Date DESC
            LIMIT 10
            """,
            (employee_id,)
        )
        
        return render_template(
            "manager/salesperson_detail.html",
            employee=employee,
            performance=performance,
            recent_orders=recent_orders
        )
    
    elif employee["Role"] == "factory_worker":
        # Factory worker performance metrics
        performance = query_db(
            """
            SELECT 
                COUNT(sp.Progress_ID) AS total_tasks,
                SUM(CASE WHEN sp.Completion_Status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
                SUM(CASE WHEN sp.Completion_Status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
                AVG(DATEDIFF(sp.Completion_Date, sp.Created_At)) AS avg_completion_days,
                MAX(sp.Completion_Date) AS last_completion_date
            FROM SECTION_PROGRESS sp
            WHERE sp.Worker_ID = %s
            """,
            (employee_id,),
            one=True
        )
        
        assigned_sections = query_db(
            """
            SELECT ps.Section_Name, ps.Section_ID,
                   COUNT(sp.Progress_ID) AS total_assigned,
                   SUM(CASE WHEN sp.Completion_Status = 'completed' THEN 1 ELSE 0 END) AS completed
            FROM SECTION_PROGRESS sp
            JOIN PRODUCTION_SECTION ps ON sp.Section_ID = ps.Section_ID
            WHERE sp.Worker_ID = %s
            GROUP BY sp.Section_ID, ps.Section_Name
            """,
            (employee_id,)
        )
        
        pending_work = query_db(
            """
            SELECT sp.Progress_ID, cp.Car_ID, cp.Order_ID, m.Model_Name, v.Variant_Name,
                   ps.Section_Name, cp.Production_Start_Date
            FROM SECTION_PROGRESS sp
            JOIN CAR_PRODUCTION cp ON sp.Car_ID = cp.Car_ID
            JOIN VARIANT v ON cp.Variant_ID = v.Variant_ID
            JOIN MODEL m ON v.Model_ID = m.Model_ID
            JOIN PRODUCTION_SECTION ps ON sp.Section_ID = ps.Section_ID
            WHERE sp.Worker_ID = %s AND sp.Completion_Status = 'pending'
            ORDER BY cp.Production_Start_Date ASC
            """,
            (employee_id,)
        )
        
        return render_template(
            "manager/factory_worker_detail.html",
            employee=employee,
            performance=performance,
            assigned_sections=assigned_sections,
            pending_work=pending_work
        )
    
    return redirect(url_for("manager_employees"))


@app.route("/manager/employees/salesperson")
@role_required("manager")
def manager_salesperson_list():
    """View all salespersons with their performance metrics"""
    dealership_filter = request.args.get("dealership_id", "")
    
    query = """
        SELECT u.User_ID, u.Name, u.Email, u.Dealership_ID, d.Name AS Dealership_Name,
               COUNT(o.Order_ID) AS total_orders,
               SUM(CASE WHEN o.Status = 'completed' THEN 1 ELSE 0 END) AS completed_orders,
               SUM(CASE WHEN o.Status = 'delivered' THEN 1 ELSE 0 END) AS delivered_orders,
               MAX(o.Order_Date) AS last_order_date,
               COUNT(DISTINCT c.Customer_ID) AS total_customers
        FROM USER u
        LEFT JOIN DEALERSHIP d ON u.Dealership_ID = d.Dealership_ID
        LEFT JOIN ORDER_TABLE o ON u.User_ID = o.Salesperson_ID
        LEFT JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
        WHERE u.Role = 'salesperson'
    """
    
    args = []
    if dealership_filter:
        query += " AND u.Dealership_ID = %s"
        args.append(dealership_filter)
    
    query += " GROUP BY u.User_ID ORDER BY u.Name"
    salespersons = query_db(query, tuple(args))
    dealerships = query_db("SELECT Dealership_ID, Name FROM DEALERSHIP ORDER BY Name")
    
    return render_template(
        "manager/salesperson_list.html",
        salespersons=salespersons,
        dealerships=dealerships,
        current_dealership=dealership_filter
    )


@app.route("/manager/employees/factory-workers")
@role_required("manager")
def manager_factory_worker_list():
    """View all factory workers with their performance metrics"""
    section_filter = request.args.get("section_id", "")
    
    query = """
        SELECT u.User_ID, u.Name, u.Email,
               COUNT(DISTINCT sp.Progress_ID) AS total_tasks,
               SUM(CASE WHEN sp.Completion_Status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
               SUM(CASE WHEN sp.Completion_Status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
               GROUP_CONCAT(DISTINCT ps.Section_Name ORDER BY ps.Section_Name) AS assigned_sections
        FROM USER u
        LEFT JOIN SECTION_PROGRESS sp ON u.User_ID = sp.Worker_ID
        LEFT JOIN PRODUCTION_SECTION ps ON sp.Section_ID = ps.Section_ID
        WHERE u.Role = 'factory_worker'
    """
    
    args = []
    if section_filter:
        query += " AND sp.Section_ID = %s"
        args.append(section_filter)
    
    query += " GROUP BY u.User_ID ORDER BY u.Name"
    factory_workers = query_db(query, tuple(args))
    production_sections = query_db("SELECT Section_ID, Section_Name FROM PRODUCTION_SECTION ORDER BY Section_Name")
    
    return render_template(
        "manager/factory_worker_list.html",
        factory_workers=factory_workers,
        production_sections=production_sections,
        current_section=section_filter
    )


@app.route("/manager/employees/add", methods=["GET", "POST"])
@role_required("manager")
def manager_add_employee():
    """Add a new employee to the system"""
    dealerships = query_db("SELECT Dealership_ID, Name FROM DEALERSHIP ORDER BY Name")
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()
        dealership_id = request.form.get("dealership_id", "").strip() if role == "salesperson" else None
        
        if not all([name, email, password, role]):
            flash("All fields are required.", "danger")
        elif role not in ["salesperson", "factory_worker"]:
            flash("Invalid role selected.", "danger")
        else:
            try:
                # Check if email already exists
                existing = query_db(
                    "SELECT User_ID FROM USER WHERE Email = %s",
                    (email,),
                    one=True
                )
                if existing:
                    flash("Email already registered in the system.", "danger")
                else:
                    # Insert new employee
                    execute_db(
                        """
                        INSERT INTO USER (Name, Email, Password, Role, Dealership_ID)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (name, email, password, role, dealership_id if dealership_id else None)
                    )
                    flash(f"Employee '{name}' added successfully!", "success")
                    return redirect(url_for("manager_employees"))
            except pymysql.Error as err:
                flash(f"Error adding employee: {err}", "danger")
    
    return render_template(
        "manager/add_employee.html",
        dealerships=dealerships
    )


# ──────────────────────────────────────────────
# Complaint Management routes
# ──────────────────────────────────────────────
@app.route("/complaints")
@login_required
def complaints():
    """View complaints - different views for different roles"""
    user_role = session.get("role")
    user_id = session.get("user_id")

    if user_role == "manager":
        # Managers see all complaints
        complaints_list = query_db("""
            SELECT c.Complaint_ID, c.Order_ID, c.Description, c.Status, c.Priority, c.Created_At,
                   c.Resolved_At, c.Resolution_Notes, cust.Name AS customer_name,
                   o.Status AS order_status, u.Name AS assigned_to_name, c.Assigned_To
            FROM COMPLAINTS c
            JOIN CUSTOMER cust ON c.Customer_ID = cust.Customer_ID
            JOIN ORDER_TABLE o ON c.Order_ID = o.Order_ID
            LEFT JOIN USER u ON c.Assigned_To = u.User_ID
            ORDER BY
                CASE c.Priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                END,
                c.Created_At DESC
        """)
        # Get all users for assignment dropdown
        users = query_db("SELECT User_ID, Name, Role FROM USER WHERE Role IN ('manager', 'salesperson') ORDER BY Name")
        return render_template("complaints.html", complaints=complaints_list, is_manager=True, users=users)

    elif user_role == "salesperson":
        # Salespeople see complaints for their orders
        complaints_list = query_db("""
            SELECT c.Complaint_ID, c.Order_ID, c.Description, c.Status, c.Priority, c.Created_At,
                   c.Resolved_At, c.Resolution_Notes, cust.Name AS customer_name,
                   o.Status AS order_status
            FROM COMPLAINTS c
            JOIN CUSTOMER cust ON c.Customer_ID = cust.Customer_ID
            JOIN ORDER_TABLE o ON c.Order_ID = o.Order_ID
            WHERE o.Salesperson_ID = %s
            ORDER BY c.Created_At DESC
        """, (user_id,))
        return render_template("complaints.html", complaints=complaints_list, is_manager=False)

    else:
        # Factory workers and others see no complaints
        return render_template("complaints.html", complaints=[], is_manager=False)


@app.route("/complaints/new", methods=["GET", "POST"])
@login_required
def new_complaint():
    """Allow customers to file complaints (via salesperson) or managers to create complaints"""
    user_role = session.get("role")

    if request.method == "POST":
        order_id = request.form.get("order_id")
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "medium")

        if not order_id or not description:
            flash("Order ID and description are required.", "danger")
            return redirect(request.url)

        # Verify the order exists and get customer info
        order = query_db("""
            SELECT o.Order_ID, o.Customer_ID, o.Salesperson_ID, o.Status
            FROM ORDER_TABLE o
            WHERE o.Order_ID = %s
        """, (order_id,), one=True)

        if not order:
            flash("Order not found.", "danger")
            return redirect(request.url)

        # Check permissions
        if user_role == "manager":
            # Managers can create complaints for any order
            pass
        elif user_role == "salesperson":
            # Salespeople can only create complaints for their orders
            if order["Salesperson_ID"] != session.get("user_id"):
                flash("You can only create complaints for your own orders.", "danger")
                return redirect(url_for("complaints"))
        else:
            flash("You don't have permission to create complaints.", "danger")
            return redirect(url_for("complaints"))

        # Create the complaint
        complaint_id = execute_db("""
            INSERT INTO COMPLAINTS (Order_ID, Customer_ID, Description, Priority)
            VALUES (%s, %s, %s, %s)
        """, (order_id, order["Customer_ID"], description, priority))

        flash(f"Complaint #{complaint_id} created successfully!", "success")
        return redirect(url_for("complaints"))

    # GET request - show form
    # Get orders based on user role
    if user_role == "manager":
        orders = query_db("""
            SELECT o.Order_ID, c.Name AS customer_name, v.Variant_Name, o.Status, o.Order_Date
            FROM ORDER_TABLE o
            JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
            JOIN VARIANT v ON o.Variant_ID = v.Variant_ID
            JOIN MODEL m ON v.Model_ID = m.Model_ID
            WHERE o.Status IN ('completed', 'delivered')
            ORDER BY o.Order_Date DESC
        """)
    elif user_role == "salesperson":
        orders = query_db("""
            SELECT o.Order_ID, c.Name AS customer_name, v.Variant_Name, o.Status, o.Order_Date
            FROM ORDER_TABLE o
            JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
            JOIN VARIANT v ON o.Variant_ID = v.Variant_ID
            JOIN MODEL m ON v.Model_ID = m.Model_ID
            WHERE o.Salesperson_ID = %s AND o.Status IN ('completed', 'delivered')
            ORDER BY o.Order_Date DESC
        """, (session.get("user_id"),))
    else:
        orders = []

    return render_template("new_complaint.html", orders=orders)


@app.route("/complaints/<int:complaint_id>/update", methods=["POST"])
@role_required("manager")
def update_complaint(complaint_id):
    """Update complaint status, assignment, and resolution"""
    status = request.form.get("status")
    assigned_to = request.form.get("assigned_to") or None
    resolution_notes = request.form.get("resolution_notes", "").strip()

    if not status:
        flash("Status is required.", "danger")
        return redirect(url_for("complaints"))

    # Update the complaint
    update_data = {"Status": status, "Assigned_To": assigned_to}
    if status in ["resolved", "closed"]:
        update_data["Resolved_At"] = "CURDATE()"
        update_data["Resolution_Notes"] = resolution_notes

    # Build the update query
    set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
    values = list(update_data.values()) + [complaint_id]

    execute_db(f"UPDATE COMPLAINTS SET {set_clause} WHERE Complaint_ID = %s", tuple(values))

    flash(f"Complaint #{complaint_id} updated successfully!", "success")
    return redirect(url_for("complaints"))


# ──────────────────────────────────────────────
# Order Management routes (Enhanced)
# ──────────────────────────────────────────────
@app.route("/manager/orders/<int:order_id>/edit", methods=["GET", "POST"])
@role_required("manager")
def manager_edit_order(order_id):
    """Allow managers to edit order details and status"""
    order = query_db("""
        SELECT o.*, c.Name AS customer_name, c.Email AS customer_email,
               v.Variant_Name, m.Model_Name, d.Name AS dealership_name
        FROM ORDER_TABLE o
        JOIN CUSTOMER c ON o.Customer_ID = c.Customer_ID
        JOIN VARIANT v ON o.Variant_ID = v.Variant_ID
        JOIN MODEL m ON v.Model_ID = m.Model_ID
        LEFT JOIN DEALERSHIP d ON c.Dealership_ID = d.Dealership_ID
        WHERE o.Order_ID = %s
    """, (order_id,), one=True)

    if not order:
        flash("Order not found.", "danger")
        return redirect(url_for("manager_dashboard"))

    if request.method == "POST":
        new_status = request.form.get("status")
        notes = request.form.get("notes", "").strip()

        if new_status and new_status != order["Status"]:
            # Update order status
            execute_db("UPDATE ORDER_TABLE SET Status = %s WHERE Order_ID = %s", (new_status, order_id))

            # If marking as delivered, update any related production records
            if new_status == "delivered":
                # Find the produced car and mark it as delivered
                produced_car = query_db("""
                    SELECT Produced_Car_ID FROM PRODUCED_CAR pc
                    JOIN CAR_PRODUCTION cp ON pc.Car_ID = cp.Car_ID
                    WHERE cp.Order_ID = %s
                """, (order_id,), one=True)
                if produced_car:
                    execute_db("UPDATE PRODUCED_CAR SET Quality_Status = 'delivered' WHERE Produced_Car_ID = %s", (produced_car["Produced_Car_ID"],))

            flash(f"Order #{order_id} status updated to '{new_status}'!", "success")
        else:
            flash("No changes made to order status.", "info")

        return redirect(url_for("manager_edit_order", order_id=order_id))

    # Get available statuses based on current status
    current_status = order["Status"]
    available_statuses = []

    if current_status == "pending":
        available_statuses = ["pending", "accepted", "cancelled"]
    elif current_status == "accepted":
        available_statuses = ["accepted", "in_production", "cancelled"]
    elif current_status == "in_production":
        available_statuses = ["in_production", "completed", "cancelled"]
    elif current_status == "completed":
        available_statuses = ["completed", "delivered", "cancelled"]
    elif current_status == "delivered":
        available_statuses = ["delivered", "returned", "cancelled"]  # Allow editing even delivered orders
    elif current_status == "cancelled":
        available_statuses = ["cancelled", "pending"]  # Allow uncancelling

    return render_template("manager/edit_order.html", order=order, available_statuses=available_statuses)


@app.route("/manager/orders/<int:order_id>/cancel", methods=["POST"])
@role_required("manager")
def manager_cancel_order(order_id):
    """Cancel an order and clean up related production if needed"""
    reason = request.form.get("reason", "").strip()

    order = query_db("SELECT Status FROM ORDER_TABLE WHERE Order_ID = %s", (order_id,), one=True)
    if not order:
        flash("Order not found.", "danger")
        return redirect(url_for("manager_dashboard"))

    if order["Status"] in ["delivered", "completed"]:
        flash("Cannot cancel a delivered or completed order.", "warning")
        return redirect(url_for("manager_dashboard"))

    # Update order status
    execute_db("UPDATE ORDER_TABLE SET Status = 'cancelled' WHERE Order_ID = %s", (order_id,))

    # If order was in production, mark car production as cancelled
    if order["Status"] == "in_production":
        execute_db("UPDATE CAR_PRODUCTION SET Status = 'cancelled' WHERE Order_ID = %s", (order_id,))

    flash(f"Order #{order_id} has been cancelled.", "success")
    return redirect(url_for("manager_dashboard"))


# ──────────────────────────────────────────────
# Account Settings routes
# ──────────────────────────────────────────────
@app.route("/account/settings", methods=["GET", "POST"])
@login_required
def account_settings():
    """Allow users to manage their account settings"""
    user_id = session.get("user_id")

    if request.method == "POST":
        action = request.form.get("action")

        if action == "change_password":
            current_password = request.form.get("current_password")
            new_password = request.form.get("new_password")
            confirm_password = request.form.get("confirm_password")

            # Verify current password
            user = query_db("SELECT Password FROM USER WHERE User_ID = %s", (user_id,), one=True)
            if not user or user["Password"] != current_password:
                flash("Current password is incorrect.", "danger")
                return redirect(request.url)

            if new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                return redirect(request.url)

            if len(new_password) < 6:
                flash("Password must be at least 6 characters long.", "danger")
                return redirect(request.url)

            # Update password
            execute_db("UPDATE USER SET Password = %s WHERE User_ID = %s", (new_password, user_id))
            flash("Password changed successfully!", "success")

        elif action == "update_profile":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()

            if not name or not email:
                flash("Name and email are required.", "danger")
                return redirect(request.url)

            # Check if email is already taken by another user
            existing = query_db("SELECT User_ID FROM USER WHERE Email = %s AND User_ID != %s", (email, user_id), one=True)
            if existing:
                flash("Email address is already in use.", "danger")
                return redirect(request.url)

            # Update profile
            execute_db("UPDATE USER SET Name = %s, Email = %s WHERE User_ID = %s", (name, email, user_id))
            session["user_name"] = name  # Update session
            flash("Profile updated successfully!", "success")

    # Get current user data
    user = query_db("SELECT Name, Email, Created_At as created_at FROM USER WHERE User_ID = %s", (user_id,), one=True)

    return render_template("account_settings.html", user=user)


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
