from flask import Flask, session, redirect, url_for, render_template, g
from auth.routes import auth_bp
from admin.routes import admin_bp
from author.routes import author_bp
from reader.routes import reader_bp
from utils import get_db_connection
from flask_mail import Mail

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# ----------------- Mail Config -----------------
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME="pushpa906690@gmail.com",
    MAIL_PASSWORD="yqwzqrgpagoasscf",
    MAIL_DEFAULT_SENDER="pushpa906690@gmail.com"
)

# Initialize Mail AFTER app config
mail = Mail(app)

# Make `mail` accessible in blueprints
app.mail = mail


# ----------------- Blueprints -----------------
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(author_bp, url_prefix='/author')
app.register_blueprint(reader_bp, url_prefix='/reader')

@app.before_request
def load_logged_in_user():
    """Load the logged-in user and store in g.user for templates"""
    user_id = session.get("user_id")
    g.user = None
    if user_id:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        g.user = cursor.fetchone()
        cursor.close()
        conn.close()

@app.route('/')
def index():
    # Always show the public landing page (index.html)
    return render_template('auth/index.html')

@app.route('/dashboard')
def dashboard():
    """Redirect users to their respective dashboards if logged in"""
    if 'user_id' in session:
        if session['user_role'] == 'admin':
            return redirect(url_for('admin.admin_dashboard'))
        else:
            return redirect(url_for('author.author_dashboard'))
    return redirect(url_for('auth.login'))

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%b %d, %Y'):
    from datetime import datetime
    if not value:
        return "N/A"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return value
    return value.strftime(format) if isinstance(value, datetime) else value

@app.before_request
def load_notifications_count():
    g.admin_notifications_count = 0
    g.reader_notifications_count = 0

    if "user_id" in session:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if session.get("user_role") == "admin":
            cursor.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE type='role_change' AND status='pending'")
            g.admin_notifications_count = cursor.fetchone()["cnt"]
        elif session.get("user_role") == "reader":
            cursor.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND status='pending'", (session["user_id"],))
            g.reader_notifications_count = cursor.fetchone()["cnt"]
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)
