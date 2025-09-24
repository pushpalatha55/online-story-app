from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, flash
from utils import get_db_connection, hash_password
import random, string
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import base64
import json
import os
from werkzeug.utils import secure_filename
from functools import wraps
from flask import g
import hashlib
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature


mail = Mail()
s = URLSafeTimedSerializer("super-secret-key")   # use app.config['SECRET_KEY'] ideally



UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
auth_bp = Blueprint('auth', __name__, url_prefix="/auth")


# ---------------- API Configuration ----------------
API_KEY = "UXFINkdiZ0h1ZmpveU5DSFpaakJmQ1ZxeTNEZXNheGZYTXVzeXd5VA=="
BASE_URL = "https://api.countrystatecity.in/v1"
HEADERS = {"X-CSCAPI-KEY": API_KEY}

# ---------------- API Routes ----------------
@auth_bp.route("/api/countries")
def api_countries():
    try:
        r = requests.get(f"{BASE_URL}/countries", headers=HEADERS, timeout=10)
        r.raise_for_status()
        countries = r.json()

        # Extract only what frontend needs
        simplified = [{"iso2": c["iso2"], "name": c["name"]} for c in countries]
        print("✅ Countries fetched:", simplified[:5])

        return jsonify(simplified)
    except Exception as e:
        print("Error fetching countries:", e)
        return jsonify([])

@auth_bp.route("/api/states/<country_code>")
def api_states(country_code):
    try:
        r = requests.get(f"{BASE_URL}/countries/{country_code}/states", headers=HEADERS, timeout=10)
        r.raise_for_status()
        states = r.json()
        simplified = [{"iso2": s["iso2"], "name": s["name"]} for s in states]
        print("✅ state fetched:", simplified[:5])
        return jsonify(simplified)
    except Exception as e:
        print("Error fetching states:", e)
        return jsonify([])

@auth_bp.route("/api/cities/<country_code>/<state_code>")
def api_cities(country_code, state_code):
    try:
        r = requests.get(f"{BASE_URL}/countries/{country_code}/states/{state_code}/cities", headers=HEADERS, timeout=10)
        r.raise_for_status()
        cities = r.json()
        simplified = [{"name": c["name"]} for c in cities]
        print("✅ City fetched:", simplified[:5])
        return jsonify(simplified)
    except Exception as e:
        print("Error fetching cities:", e)
        return jsonify([])


# ---------------- Register ----------------
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        phone = request.form["phone"]
        gender = request.form.get("gender")
        roles = request.form.getlist("roles")
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        country = request.form["country"]
        state = request.form["state"]
        city = request.form["city"]

        if password != confirm_password:
            error = "Passwords do not match"
        elif len(password) < 6:
            error = "Password must be at least 6 characters"
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
            if cursor.fetchone():
                error = "Username or Email already exists"
            else:
                hashed = hash_password(password)
                role_str = ",".join(roles) if roles else "reader"
                cursor.execute(
                    """INSERT INTO users 
                       (username, email, phone, gender, roles, password_hash, country, state, city) 
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (username, email, phone, gender, role_str, hashed, country, state, city)
                )
                conn.commit()
                cursor.close()
                conn.close()
                return redirect(url_for("auth.login"))

            cursor.close()
            conn.close()

    return render_template("auth/register.html", error=error)

@auth_bp.route("/register-success")
def register_success():
    return "Registration successful!"


# ---------------- Profile ----------------
@auth_bp.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
    user = cursor.fetchone()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_photo":
            profile_pic = request.files.get("profile_pic")
            if profile_pic and profile_pic.filename:
                filename = secure_filename(profile_pic.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                profile_pic.save(filepath)
                cursor.execute("UPDATE users SET profile_pic=%s WHERE id=%s", (filename, user["id"]))
                conn.commit()
                flash("Profile photo updated successfully!", "success")
        elif action == "delete_photo":
            if user["profile_pic"]:
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, user["profile_pic"]))
                except:
                    pass
            cursor.execute("UPDATE users SET profile_pic=NULL WHERE id=%s", (user["id"],))
            conn.commit()
            flash("Profile photo deleted successfully!", "info")

        cursor.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
        user = cursor.fetchone()

    cursor.close()
    conn.close()
    return render_template("auth/profile.html", user=user)



# ---------------- Custom login_required ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

# ---------------- Helper: Get Current User ----------------
def get_current_user():
    if "user_id" not in session:
        return None
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

# ---------------- Edit Account ----------------
@auth_bp.route("/edit-account", methods=["GET", "POST"])   # ✅ FIXED (added @)
@login_required
def edit_account():
    user = get_current_user()
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        phone = request.form.get("phone")
        gender = request.form.get("gender")
        roles = request.form.getlist("roles")
        country = request.form.get("country")
        state = request.form.get("state")
        city = request.form.get("city")

        # Handle profile picture upload
        profile_pic = request.files.get("profile_pic")
        filename = user["profile_pic"]
        if profile_pic and profile_pic.filename:
            filename = secure_filename(profile_pic.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            profile_pic.save(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE users 
               SET username=%s, phone=%s, gender=%s, roles=%s, 
                   country=%s, state=%s, city=%s, profile_pic=%s 
               WHERE id=%s""",
            (username, phone, gender, ",".join(roles), country, state, city, filename, user["id"])
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash("Account updated successfully!", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/edit_account.html", user=user, error=error)


# ---------------- Change Password ----------------
def hash_sha256(password):
    return hashlib.sha256(password.encode()).hexdigest()

@auth_bp.route("/change_password", methods=["GET", "POST"])
def change_password():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT id, password_hash FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return render_template("auth/change_password.html", error="User not found")

        if request.method == "POST":
            current_password = request.form["current_password"].strip()
            new_password = request.form["new_password"].strip()
            confirm_password = request.form["confirm_password"].strip()

            # Check current password
            if hash_sha256(current_password) != user["password_hash"]:
                return render_template("auth/change_password.html", error="Current password is incorrect")

            if new_password != confirm_password:
                return render_template("auth/change_password.html", error="New passwords do not match")

            if len(new_password) < 6:
                return render_template("auth/change_password.html", error="Password must be at least 6 characters")

            # Update password
            new_hash = hash_sha256(new_password)
            cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, user_id))
            conn.commit()

            flash("Password changed successfully!", "success")
            return redirect(url_for("auth.change_password"))

        return render_template("auth/change_password.html")

    finally:
        cursor.close()
        conn.close()





# ---------------- Login ----------------
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if "captcha_code" not in session:
        session["captcha_code"] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        captcha_input = request.form.get("captcha", "").strip()

        # Check captcha
        if captcha_input != session.get("captcha_code"):
            error = "Invalid captcha. Please try again."
            session["captcha_code"] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            return render_template("auth/login.html", error=error, captcha_code=session["captcha_code"])

        # Fetch user from DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        # Verify password
        if user and user['password_hash'] == hash_password(password):
            # ✅ Blocked/Suspended check
            if user['status'] in ['blocked', 'suspended']:
                error = "Your account has been blocked or suspended. Please contact the administrator."
                session["captcha_code"] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
                return render_template("auth/login.html", error=error, captcha_code=session["captcha_code"])

            # ✅ Store session info
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['city'] = user.get('city')   # ✅ Added: store city for weather

            # Handle multiple roles correctly (author > reader priority)
            roles_list = (user.get('roles') or '').split(',')  # split by comma
            roles_list = [r.strip() for r in roles_list if r.strip()]  # clean spaces

            if "admin" in roles_list:
                primary_role = "admin"
            elif "author" in roles_list:
                primary_role = "author"
            elif "reader" in roles_list:
                primary_role = "reader"
            else:
                primary_role = user.get('role', 'reader')  # fallback

            session['user_role'] = primary_role

            # Reset captcha
            session["captcha_code"] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

            # Redirect based on role
            if session['user_role'] == 'admin':
                return redirect(url_for('admin.admin_dashboard'))
            elif session['user_role'] == 'author':
                return redirect(url_for('author.author_dashboard'))
            elif session['user_role'] == 'reader':
                return redirect(url_for('reader.reader_dashboard'))
            else:
                return redirect(url_for('reader.reader_dashboard'))  # default fallback
        else:
            error = 'Invalid credentials'
            session["captcha_code"] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

    return render_template('auth/login.html', error=error, captcha_code=session["captcha_code"])



@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    error = None
    success = None

    if request.method == 'POST':
        email = request.form['email'].strip()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            # Generate secure token
            token = s.dumps(email, salt="password-reset-salt")
            reset_url = url_for("auth.reset_password", token=token, _external=True)

            # Send email
            msg = Message("Password Reset Request", recipients=[email])
            msg.body = f"Hi {user['username']},\n\nClick below to reset your password:\n{reset_url}\n\nIf you didn’t request this, ignore this email."
            mail.send(msg)

            success = "A password reset link has been sent to your email."
        else:
            error = "No account found with that email."

    return render_template("auth/forgot_password.html", error=error, success=success)



@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    error = None
    success = None

    try:
        email = s.loads(token, salt="password-reset-salt", max_age=3600)  # 1 hour
    except SignatureExpired:
        error = "The reset link has expired."
        return render_template("auth/reset_password.html", error=error)
    except BadSignature:
        error = "Invalid reset link."
        return render_template("auth/reset_password.html", error=error)

    if request.method == "POST":
        password = request.form["password"].strip()
        confirm_password = request.form["confirm_password"].strip()

        if password != confirm_password:
            error = "Passwords do not match"
        elif len(password) < 6:
            error = "Password must be at least 6 characters"
        else:
            # Update DB
            conn = get_db_connection()
            cursor = conn.cursor()
            hashed = hash_password(password)
            cursor.execute("UPDATE users SET password_hash = %s WHERE email = %s", (hashed, email))
            conn.commit()
            cursor.close()
            conn.close()

            success = "Password reset successful! You can now log in."
            return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", error=error, success=success)



from flask import current_app as app
from flask_mail import Message

def send_reset_email(to_email, token):
    reset_link = url_for('auth.reset_password', token=token, _external=True)
    msg = Message(
        subject="Password Reset Request",
        recipients=[to_email],
        body=f"Hello,\n\nClick the link below to reset your password:\n{reset_link}\n\nIf you didn't request this, ignore this email."
    )
    app.mail.send(msg)



def generate_reset_token(user_id):
    # Implement token generation logic
    return "mock_token"

def verify_reset_token(token):
    # Implement token verification logic
    return 1  # Mock user ID



@auth_bp.route('/switch_dashboard')
def switch_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    current_role = session.get('user_role')

    # ✅ If admin → switch to author
    if current_role == 'admin':
        session['original_role'] = 'admin'   # store the real role
        session['user_role'] = 'author'
        return redirect(url_for('author.author_dashboard'))

    # ✅ If author but originally admin → switch back to admin
    elif current_role == 'author' and session.get('original_role') == 'admin':
        session['user_role'] = 'admin'
        session.pop('original_role', None)   # cleanup flag
        return redirect(url_for('admin.admin_dashboard'))

    # ❌ Block normal authors from switching
    flash("You are not allowed to switch dashboards.", "danger")
    return redirect(url_for('auth.profile'))


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/')
def index():
    return render_template("auth/index.html")

@auth_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')

        print(f"New message from {name} ({email}): {message}")
        return redirect(url_for('auth.thank_you', name=name))

    return render_template('auth/contact.html')

@auth_bp.route('/thank-you')
def thank_you():
    name = request.args.get('name')
    print(f"New message from {name}")
    return render_template('auth/thank_you.html', name=name)

# Define the route for the about page
@auth_bp.route('/about')
def about():
    """Renders the about page."""
    return render_template('auth/about.html')

@auth_bp.route('/all_stories')
def all_stories():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch author name + profile pic
    cursor.execute('''
        SELECT s.*, 
               u.username AS author_name, 
               u.profile_pic AS author_profile_pic
        FROM stories s 
        JOIN users u ON s.author_id = u.id 
        WHERE s.status = 'published' 
        ORDER BY s.publish_date DESC
    ''')
    
    stories = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('auth/all_stories.html', stories=stories)