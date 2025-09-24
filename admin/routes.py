from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, send_file, current_app,flash
from utils import get_db_connection
import os
from werkzeug.utils import secure_filename
import io, csv
from reportlab.pdfgen import canvas
from datetime import datetime

admin_bp = Blueprint('admin', __name__)


# ---------------- Admin Dashboard ----------------
@admin_bp.route('/dashboard')
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Stats cards
    cursor.execute("""
        SELECT SUM(views) as total_views, SUM(likes) as total_likes, SUM(comments) as total_comments 
        FROM stories
    """)
    stats = cursor.fetchone()
    stats["avg_engagement"] = round(
        ((stats["total_likes"] + stats["total_comments"]) / stats["total_views"]) * 100, 2
    ) if stats["total_views"] else 0

    # Top performing stories
    cursor.execute("""
        SELECT s.title, u.username as author, s.views, 
               ROUND(((s.likes + s.comments) / GREATEST(s.views,1)) * 100, 2) as engagement
        FROM stories s
        JOIN users u ON s.author_id = u.id
        ORDER BY s.views DESC
        LIMIT 5
    """)
    top_stories = cursor.fetchall()

    # Author performance
    cursor.execute("""
        SELECT u.username as name, u.profile_pic,
               COUNT(s.id) as stories,
               AVG(s.views) as avg_views,
               ROUND(AVG((s.likes + s.comments) / GREATEST(s.views,1)) * 100, 2) as avg_engagement
        FROM users u
        JOIN stories s ON u.id = s.author_id
        WHERE u.role = 'author'
        GROUP BY u.id
        ORDER BY avg_views DESC
        LIMIT 5
    """)
    author_performance = cursor.fetchall()

    # Content distribution
    cursor.execute("""
    SELECT s.category as category, COUNT(s.id) as story_count
    FROM stories s
    WHERE s.category IS NOT NULL
    GROUP BY s.category
    """)
    categories = cursor.fetchall()
    content_labels = [c["category"] for c in categories]
    content_counts = [c["story_count"] for c in categories]

    if not any(content_counts):  
        content_labels = []
        content_counts = []

    # Gender distribution
    cursor.execute("SELECT gender, COUNT(*) as count FROM users WHERE gender IS NOT NULL GROUP BY gender")
    genders = cursor.fetchall()
    gender_labels = [g["gender"] for g in genders]
    gender_counts = [g["count"] for g in genders]

    # Top locations
    cursor.execute("""
        SELECT country, COUNT(*) as count 
        FROM users 
        WHERE country IS NOT NULL 
        GROUP BY country 
        ORDER BY count DESC 
        LIMIT 5
    """)
    locs = cursor.fetchall()
    total_users = sum([l["count"] for l in locs]) or 1
    top_locations = [{"country": l["country"], "percentage": round((l["count"]/total_users)*100, 2)} for l in locs]

    cursor.close()
    conn.close()

    return render_template("admin/admin_dashboard.html",
                           stats=stats,
                           top_stories=top_stories,
                           author_performance=author_performance,
                           content_labels=content_labels,
                           content_counts=content_counts,
                           gender_labels=gender_labels,
                           gender_counts=gender_counts,
                           top_locations=top_locations)

from datetime import date, timedelta

@admin_bp.route('/traffic_data')
def traffic_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ✅ Get last 30 days only
    cursor.execute("""
        SELECT DATE(updated_at) as date,   -- 🔄 use updated_at instead of created_at
               SUM(views) as views,
               SUM(likes) as likes,
               SUM(comments) as comments
        FROM stories
        WHERE updated_at >= CURDATE() - INTERVAL 29 DAY
        GROUP BY DATE(updated_at)
        ORDER BY date
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # ✅ Build a continuous date list (always includes today)
    today = date.today()
    days = [(today - timedelta(days=i)) for i in range(5, -1, -1)]

    data_map = {str(r["date"]): r for r in rows}

    labels, views, likes, comments = [], [], [], []
    for d in days:
        d_str = str(d)
        labels.append(d_str)
        views.append(data_map.get(d_str, {}).get("views", 0))
        likes.append(data_map.get(d_str, {}).get("likes", 0))
        comments.append(data_map.get(d_str, {}).get("comments", 0))

    return jsonify({
        "labels": labels,
        "views": views,
        "likes": likes,
        "comments": comments
    })


# ---------------- Top Locations Data API ----------------
@admin_bp.route('/top_locations_data')
def top_locations_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT country, COUNT(*) as count 
        FROM users 
        WHERE country IS NOT NULL 
        GROUP BY country 
        ORDER BY count DESC 
        LIMIT 5
    """)
    rows = cursor.fetchall()
    labels = [r["country"] for r in rows]
    data = [r["count"] for r in rows]
    cursor.close()
    conn.close()
    return jsonify({"labels": labels, "data": data})

# ---------------- Top Stories Data API ----------------
@admin_bp.route('/top_stories_data')
def top_stories_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.title, s.views 
        FROM stories s
        JOIN users u ON s.author_id = u.id
        ORDER BY s.views DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()
    labels = [r["title"] for r in rows]
    data = [r["views"] for r in rows]
    cursor.close()
    conn.close()
    return jsonify({"labels": labels, "data": data})

# ---------------- Top Authors Data API ----------------
@admin_bp.route('/top_authors_data')
def top_authors_data():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.username as name, u.profile_pic, AVG(s.views) as avg_views
        FROM users u
        JOIN stories s ON u.id = s.author_id
        WHERE u.role='author'
        GROUP BY u.id
        ORDER BY avg_views DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()
    labels = [r["name"] for r in rows]
    data = [round(r["avg_views"], 2) for r in rows]
    images = [r["profile_pic"] or "/static/uploads/default.png" for r in rows]
    cursor.close()
    conn.close()
    return jsonify({"labels": labels, "data": data, "images": images})


    


@admin_bp.route('/users')
def user_management():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get ALL users with their story counts
    query = '''
        SELECT u.id, u.username, u.email, u.role, u.roles, u.status, u.profile_pic, u.created_at,
               COUNT(s.id) AS story_count
        FROM users u
        LEFT JOIN stories s ON u.id = s.author_id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    '''
    cursor.execute(query)
    users = cursor.fetchall()

    # Get user statistics
    cursor.execute('SELECT COUNT(*) as total_users FROM users')
    stats_total_users = cursor.fetchone()['total_users']
    
    cursor.execute('SELECT COUNT(*) as active_users FROM users WHERE status = "active"')
    active_users = cursor.fetchone()['active_users']
    
    cursor.execute("SELECT COUNT(*) as total_authors FROM users WHERE roles LIKE '%author%'")
    total_authors = cursor.fetchone()['total_authors']
    
    # Modified line to count both blocked and suspended users
    cursor.execute('SELECT COUNT(*) as blocked_users FROM users WHERE status IN ("blocked", "suspended")')
    blocked_users = cursor.fetchone()['blocked_users']
    
    cursor.close()
    conn.close()
    
    stats = {
        'total_users': stats_total_users,
        'active_users': active_users,
        'total_authors': total_authors,
        'blocked_users': blocked_users
    }
    
    return render_template(
        'admin/user_management.html',
        users=users,
        stats=stats,
        username=session['username']
    )




# -------------------- Browse Stories --------------------
# -------------------- Browse Stories --------------------
@admin_bp.route('/browse-stories')
def browse_stories():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        return redirect(url_for('auth.login'))
    
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 12

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # --- Base Query ---
        query = '''
            SELECT s.*, u.username as author_name, u.email as author_email, u.profile_pic as author_profile_pic, c.name as category_name
            FROM stories s 
            JOIN users u ON s.author_id = u.id
            LEFT JOIN categories c ON s.category_id = c.id
        '''

        where_clauses = []
        params = []
        
        # Status filter
        if status_filter:
            where_clauses.append('s.status = %s')
            params.append(status_filter)
        
        # Category filter (use category name from categories table)
        if category_filter:
            where_clauses.append('c.name = %s')
            params.append(category_filter)
        
        # Search filter
        if search_query:
            where_clauses.append('(s.title LIKE %s OR s.content LIKE %s OR u.username LIKE %s)')
            params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])
        
        # Apply filters
        if where_clauses:
            query += ' WHERE ' + ' AND '.join(where_clauses)
        
        query += ' ORDER BY s.created_at DESC'
        
        # --- Count total ---
        count_query = '''
            SELECT COUNT(*) as total 
            FROM stories s 
            JOIN users u ON s.author_id = u.id
            LEFT JOIN categories c ON s.category_id = c.id
        '''
        if where_clauses:
            count_query += ' WHERE ' + ' AND '.join(where_clauses)
        
        cursor.execute(count_query, params)
        total_stories = cursor.fetchone()['total']
        
        # --- Pagination ---
        query += ' LIMIT %s OFFSET %s'
        params.extend([per_page, (page - 1) * per_page])
        
        cursor.execute(query, params)
        stories = cursor.fetchall()

        # --- Fetch all categories from categories table for dropdown ---
        cursor.execute("SELECT name FROM categories ORDER BY name ASC")
        categories = [row['name'] for row in cursor.fetchall()]
    
    except Exception as e:
        print(f"Database error: {e}")
        stories = []
        total_stories = 0
        categories = []
    
    finally:
        cursor.close()
        conn.close()
    
    # Pagination dictionary
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_stories,
        'pages': (total_stories + per_page - 1) // per_page,
        'has_prev': page > 1,
        'has_next': page * per_page < total_stories,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return render_template('admin/browse_stories.html', 
                           stories=stories,
                           pagination=pagination,
                           categories=categories,              # ✅ Pass categories to template
                           selected_category=category_filter,  # ✅ Pass current filter
                           search_query=search_query,
                           status_filter=status_filter,
                           username=session['username'])





# ---------- Preview route (matches JS: /admin/stories/<id>) ----------
@admin_bp.route('/stories/<int:story_id>')
def story_preview(story_id):
    print("Preview requested for story_id:", story_id)  # DEBUG LOG

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
            SELECT s.*, u.username as author_name, u.email as author_email
            FROM stories s 
            JOIN users u ON s.author_id = u.id
            WHERE s.id = %s
        ''', (story_id,))
        story = cursor.fetchone()
        print("Fetched story:", story)  # DEBUG LOG

        if not story:
            return jsonify({'error': 'Not found'}), 404

        # Make sure featured_image is properly served via /static
        if story.get('featured_image'):
            # Check if the DB has just the filename (e.g., 'image.jpg')
            # or already includes 'uploads/'. Adjust accordingly.
            if story['featured_image'].startswith('uploads/'):
                # DB already stores 'uploads/image.jpg'
                story['featured_image_url'] = f"/static/{story['featured_image']}"
            else:
                # DB stores only the filename
                story['featured_image_url'] = f"/static/uploads/{story['featured_image']}"
        else:
            story['featured_image_url'] = ""  # Empty if no image

        # Optional: format created_at for display
        if story.get('created_at'):
            story['created_at'] = story['created_at'].strftime('%b %d, %Y %H:%M')

        return jsonify(story)

    except Exception as e:
        print("story_preview error:", e)  # DEBUG LOG
        return jsonify({'error': 'Server error'}), 500
    finally:
        cursor.close()
        conn.close()




# ---------- NEW: Export routes ----------
@admin_bp.route('/stories/export/csv')
def export_stories_csv():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, title, category, status, created_at FROM stories ORDER BY created_at DESC')
        rows = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Title', 'Category', 'Status', 'Created At'])
        for r in rows:
            # r is a tuple from non-dict cursor
            writer.writerow(r)
        output.seek(0)

        mem = io.BytesIO()
        mem.write(output.getvalue().encode('utf-8'))
        mem.seek(0)

        filename = f"stories_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=filename)
    except Exception as e:
        print("export_stories_csv error:", e)
        return "Export failed", 500
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/stories/export/pdf')
def export_stories_pdf():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, title, category, status, created_at FROM stories ORDER BY created_at DESC LIMIT 200')
        rows = cursor.fetchall()

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer)
        p.setFont("Helvetica", 12)
        p.drawString(40, 820, "Stories Report")
        y = 800
        for r in rows:
            line = f"{r['id']} | {r['title'][:80]} | {r['category'] or ''} | {r['status']} | {r['created_at']}"
            p.drawString(40, y, line)
            y -= 16
            if y < 60:
                p.showPage()
                y = 800
        p.save()
        buffer.seek(0)
        filename = f"stories_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
    except Exception as e:
        print("export_stories_pdf error:", e)
        return "Export failed", 500
    finally:
        cursor.close()
        conn.close()



# -------------------- Notifications Dashboard --------------------
@admin_bp.route("/notifications")
def notifications():
    if "user_id" not in session or session.get("user_role") != "admin":
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Author role change notifications
        cursor.execute("""
            SELECT n.id, n.message, n.status, n.created_at, u.username
            FROM notifications n
            JOIN users u ON n.user_id = u.id
            WHERE n.type = 'role_change'
            ORDER BY n.created_at DESC
        """)
        author_notifications = cursor.fetchall()

        # Reader notifications
        cursor.execute("""
            SELECT n.id, n.message, n.status, n.created_at, u.username
            FROM notifications n
            JOIN users u ON n.user_id = u.id
            WHERE n.type = 'reader_message'
            ORDER BY n.created_at DESC
        """)
        reader_notifications = cursor.fetchall()

        # Author messages
        cursor.execute("""
            SELECT n.id, n.message, n.status, n.created_at, u.username
            FROM notifications n
            JOIN users u ON n.user_id = u.id
            WHERE n.type = 'message'
            ORDER BY n.created_at DESC
        """)
        author_messages = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template(
        "admin/notifications.html",
        author_notifications=author_notifications,
        reader_notifications=reader_notifications,
        author_messages=author_messages
    )

# -------------------- Approve Request --------------------
@admin_bp.route("/notifications/<int:note_id>/approve", methods=["POST"])
def approve_notification(note_id):
    if "user_id" not in session or session.get("user_role") != "admin":
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id FROM notifications WHERE id=%s AND status='pending'", (note_id,))
        note = cursor.fetchone()
        if not note:
            flash("Request not found or already handled.", "warning")
            return redirect(url_for("admin.notifications"))

        user_id = note["user_id"]
        cursor.execute("UPDATE notifications SET status='approved' WHERE id=%s", (note_id,))
        cursor.execute("SELECT roles FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        roles = (user["roles"] or "").split(",")
        if "author" not in roles:
            roles.append("author")
        new_roles = ",".join(filter(None, roles))
        cursor.execute("UPDATE users SET roles=%s WHERE id=%s", (new_roles, user_id))

        conn.commit()
        flash("User has been approved as Author.", "success")

        if session.get("user_id") == user_id:
            session['user_role'] = 'author'
            flash("Your account is now upgraded to Author!", "success")
            return redirect(url_for('author.author_dashboard'))
    except Exception as e:
        conn.rollback()
        flash("Error approving request: " + str(e), "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin.notifications"))

# -------------------- Reject Request --------------------
@admin_bp.route("/notifications/<int:note_id>/reject", methods=["POST"])
def reject_notification(note_id):
    if "user_id" not in session or session.get("user_role") != "admin":
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE notifications SET status='rejected' WHERE id=%s AND status='pending'", (note_id,))
        conn.commit()
        flash("Request has been rejected.", "info")
    except Exception as e:
        conn.rollback()
        flash("Error rejecting request: " + str(e), "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin.notifications"))

@admin_bp.route("/notifications/<int:note_id>/reply", methods=["POST"])
def reply_to_author(note_id):
    if "user_id" not in session or session.get("user_role") != "admin":
        flash("You must be logged in as an Admin.", "warning")
        return redirect(url_for("auth.login"))

    reply_message = request.form.get("reply_message", "").strip()
    if not reply_message:
        flash("Reply cannot be empty.", "danger")
        return redirect(url_for("admin.notifications"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get original author's id
        cursor.execute("SELECT user_id FROM notifications WHERE id=%s", (note_id,))
        note = cursor.fetchone()
        if not note:
            flash("Original message not found.", "warning")
            return redirect(url_for("admin.notifications"))

        author_id = note["user_id"]
        admin_id = session["user_id"]

        # Insert reply **as created by admin**
        cursor.execute("""
            INSERT INTO notifications (user_id, type, message, status)
            VALUES (%s, 'reply', %s, 'unread')
        """, (admin_id, reply_message))
        conn.commit()
        flash("Reply sent to the author!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error sending reply: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin.notifications"))




# ---------------- Delete User ----------------
@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    # Ensure only admins can delete
    if session.get("user_role") != "admin":
        return {"success": False, "message": "Unauthorized"}, 403

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True, "message": "User deleted successfully"}
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return {"success": False, "message": str(e)}, 500
    

@admin_bp.route('/stories/<int:story_id>/delete', methods=['POST'])
def story_delete(story_id):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT featured_image FROM stories WHERE id = %s', (story_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        featured_image = row.get('featured_image')

        # Delete DB row
        cursor.execute('DELETE FROM stories WHERE id = %s', (story_id,))
        conn.commit()

        # Remove image file if exists
        if featured_image:
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            file_path = os.path.join(upload_folder, featured_image)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print("Failed to remove image:", e)

        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        print("story_delete error:", e)
        return jsonify({'success': False, 'error': 'Server error'}), 500
    finally:
        cursor.close()
        conn.close()



# List all categories
@admin_bp.route('/manage_categories')
def manage_categories():
    if session.get('user_role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM categories ORDER BY name ASC")
    categories = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('admin/manage_categories.html', categories=categories)


# Add new category
@admin_bp.route('/category/add', methods=['POST'])
def add_category():
    if session.get('user_role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('auth.login'))
    
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Category name is required', 'error')
        return redirect(url_for('admin.manage_categories'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (name, description) VALUES (%s, %s)", (name, description))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Category added successfully!', 'success')
    return redirect(url_for('admin.manage_categories'))


# Edit category
@admin_bp.route('/category/<int:category_id>/edit', methods=['POST'])
def edit_category(category_id):
    if session.get('user_role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('auth.login'))
    
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Category name is required', 'error')
        return redirect(url_for('admin.manage_categories'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE categories SET name=%s, description=%s WHERE id=%s", (name, description, category_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Category updated successfully!', 'success')
    return redirect(url_for('admin.manage_categories'))


# Delete category
@admin_bp.route('/category/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    if session.get('user_role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM categories WHERE id=%s", (category_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('admin.manage_categories'))



@admin_bp.route('/update_user_status/<int:user_id>/<string:new_status>')
def update_user_status(user_id, new_status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status=%s WHERE id=%s", (new_status, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"User status updated to {new_status}", "success")
    return redirect(url_for('admin.user_management'))
