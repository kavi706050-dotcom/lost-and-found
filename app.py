from flask import Flask, render_template, request, redirect, session
import sqlite3, os, random

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------- DATABASE ----------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category TEXT,
        date TEXT,
        description TEXT,
        image TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        sender TEXT,
        message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    db.commit()
    db.close()

init_db()

def migrate_db():
    db = get_db()
    try:
        db.execute("ALTER TABLE items ADD COLUMN reporter_id TEXT")
    except:
        pass
    try:
        db.execute("ALTER TABLE items ADD COLUMN owner_email TEXT")
    except:
        pass
    try:
        db.execute("ALTER TABLE items ADD COLUMN location TEXT")
        db.commit()
    except:
        pass
    db.close()

migrate_db()

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        db = get_db()
        db.execute("INSERT OR IGNORE INTO users(email) VALUES(?)", (email,))
        db.commit()
        db.close()
        session["email"] = email
        return redirect("/home")
    return render_template("login.html")

# ---------- HOME ----------
@app.route("/home")
def home():
    if "email" not in session:
        return redirect("/")
    db = get_db()
    items = db.execute("SELECT * FROM items").fetchall()
    db.close()
    return render_template("home.html", items=items, user=session.get("email"))

# ---------- ADD ITEM ----------
@app.route("/add", methods=["GET", "POST"])
def add():
    if "email" not in session:
        return redirect("/")
    if request.method == "POST":
        image = request.files["image"]
        filename = image.filename
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db = get_db()
        db.execute("""
        INSERT INTO items(name,category,date,description,image,status,reporter_id,owner_email)
        VALUES(?,?,?,?,?,?,?,?)
        """, (
            request.form["name"],
            request.form["category"],
            request.form["date"],
            request.form["description"],
            filename,
            "pending",
            request.form["reporter_id"],
            session["email"]
        ))
        db.commit()
        db.close()
        return redirect("/home")
    return render_template("add.html")

# ---------- ADMIN ----------
@app.route("/admin")
def admin():
    db = get_db()
    items = db.execute("SELECT * FROM items").fetchall()
    db.close()
    return render_template("admin.html", items=items)

@app.route("/approve/<int:item_id>", methods=["GET", "POST"])
def approve(item_id):
    if "email" not in session:
        return redirect("/")

    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    
    # Permission Check (Specific Admin Only)
    if session['email'] != 'laptopa321ba@gmail.com':
        db.close()
        return redirect("/home") 

    if request.method == "POST":
        image = request.files["image"]
        desc = request.form["description"]

        filename = "verify_" + image.filename
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        # -------- AI MATCH SCORE (SIMULATED) --------
        # Simulate matching logic: 
        # In a real app, we'd compare image features and text vectors.
        # Here we use a weighted random score based on description length presence.
        
        base_score = random.randint(75, 99) if len(desc) > 10 else random.randint(40, 60)
        
        # Save the score as a percentage string
        status = f"{base_score}%"

        db.execute(
            "UPDATE items SET status=? WHERE id=?",
            (status, item_id)
        )
        db.commit()
        db.close()

        return render_template("match_result.html", item=item, score=base_score, verify_img=filename)

    db.close()
    return render_template("approve.html", item=item)


# ---------- EDIT ITEM (ADMIN ONLY) ----------
@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
def edit(item_id):
    if "email" not in session:
        return redirect("/")
    
    # Strict Admin Check
    if session['email'] != 'laptopa321ba@gmail.com':
        return redirect("/home")

    db = get_db()
    
    if request.method == "POST":
        name = request.form["name"]
        category = request.form["category"]
        date = request.form["date"]
        desc = request.form["description"]
        rep_id = request.form["reporter_id"]
        location = request.form.get("location", "")
        
        # Handle Image Update
        image_file = request.files["image"]
        if image_file and image_file.filename != "":
            filename = image_file.filename
            image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            db.execute("UPDATE items SET image=? WHERE id=?", (filename, item_id))

        db.execute("""
            UPDATE items 
            SET name=?, category=?, date=?, description=?, reporter_id=?, location=?
            WHERE id=?
        """, (name, category, date, desc, rep_id, location, item_id))
        
        db.commit()
        db.close()
        return redirect("/home")

    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    db.close()
    return render_template("edit.html", item=item)


# ---------- APPROVE / REJECT ----------
@app.route("/update_status/<int:item_id>/<string:status>")
def update_status(item_id, status):
    if status != "approved":
        return redirect("/admin")

    db = get_db()
    db.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
    db.commit()
    db.close()
    return redirect("/admin")

# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    
    # helper to check if a status string counts as approved
    def is_approved(s):
        if not s: return False
        if s == 'approved': return True
        if s.endswith('%'):
            try:
                val = int(s.rstrip('%'))
                return val >= 70
            except:
                return False
        return False

    def is_rejected(s):
        if not s: return False
        if s in ['rejected', 'fake']: return True
        if s.endswith('%'):
            try:
                val = int(s.rstrip('%'))
                return val < 70
            except:
                return False
        return False
        
    all_items = db.execute("SELECT status FROM items").fetchall()
    db.close()

    approved = sum(1 for row in all_items if is_approved(row['status']))
    rejected = sum(1 for row in all_items if is_rejected(row['status']))

    ai_score = int((approved / total) * 100) if total else 0

    return render_template(
        "dashboard.html",
        total=total,
        approved=approved,
        rejected=rejected,
        ai_score=ai_score
    )

# ---------- CHAT ----------
@app.route("/chat/<int:item_id>", methods=["GET", "POST"])
def chat(item_id):
    if "email" not in session:
        return redirect("/")
    
    db = get_db()
    
    if request.method == "POST":
        msg = request.form["message"]
        sender = session["email"]
        db.execute("INSERT INTO messages (item_id, sender, message) VALUES (?, ?, ?)", 
                   (item_id, sender, msg))
        db.commit()
    
    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    messages = db.execute("SELECT * FROM messages WHERE item_id=? ORDER BY timestamp ASC", (item_id,)).fetchall()
    db.close()
    
    return render_template("chat.html", item=item, messages=messages, user=session["email"])

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")



if __name__ == "__main__":
    app.run(debug=True)
