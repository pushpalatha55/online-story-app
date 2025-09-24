from flask import Blueprint, render_template, session, redirect, url_for, request,jsonify,flash
from utils import get_db_connection
import json

reader_bp = Blueprint("reader", __name__, url_prefix="/reader")


def get_reader_stats(user_id):
    """Fetch reader stats: stories read, likes, comments."""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Count likes and comments by the user
    cursor.execute("""
        SELECT
            (SELECT COUNT(*) FROM likes WHERE user_id=%s) AS likes_given,
            (SELECT COUNT(*) FROM comments WHERE user_id=%s) AS comments_count,
            (SELECT COUNT(DISTINCT story_id) FROM likes WHERE user_id=%s) +
            (SELECT COUNT(DISTINCT story_id) FROM comments WHERE user_id=%s) AS stories_read
    """, (user_id, user_id, user_id, user_id))
    
    stats = cursor.fetchone() or {}
    cursor.close()
    db.close()
    
    return {
        "likes_given": stats.get("likes_given", 0),
        "comments_count": stats.get("comments_count", 0),
        "stories_read": stats.get("stories_read", 0)
    }


# -------------------- Reader Dashboard --------------------
@reader_bp.route("/dashboard")
def reader_dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Reader stats
    reader_stats = get_reader_stats(user_id)
    
    # Generate data for the reading stats graph
    reading_graph_data = {
        "labels": ["Stories Read", "Likes Given", "Comments"],
        "data": [
            reader_stats.get("stories_read", 0),
            reader_stats.get("likes_given", 0),
            reader_stats.get("comments_count", 0)
        ],
        "colors": ["#4e73df", "#1cc88a", "#36b9cc"]
    }

    # Featured stories (latest 6)
    cursor.execute("""
        SELECT s.id, s.title, s.content, s.featured_image, s.category, s.views,
               u.username AS author,
               (SELECT COUNT(*) FROM likes WHERE story_id = s.id) AS likes,
               (SELECT COUNT(*) FROM comments WHERE story_id = s.id) AS comments
        FROM stories s
        JOIN users u ON s.author_id = u.id
        ORDER BY s.created_at DESC
        LIMIT 6
    """)
    featured_stories = cursor.fetchall()
    for story in featured_stories:
        story["description"] = (story["content"] or "")[:120]

    # -------------------- Categories Section --------------------
    # Fetch top 8 categories by story count (using category name text)
    cursor.execute("""
        SELECT c.name, COUNT(s.id) AS total
        FROM categories c
        LEFT JOIN stories s ON s.category = c.name
        GROUP BY c.name
        ORDER BY total DESC
        LIMIT 8
    """)
    categories = cursor.fetchall()

    # Map categories to images (without changing database)
    category_images = {
        "Fantasy": "/static/images/categories/fantacy.jpg",
        "Science Fiction": "/static/images/categories/non-fiction.jpg",
        "Mystery": "/static/images/categories/mystery.jpg",
        "Romance": "/static/images/categories/romantic.jpg",
        "Adventure": "/static/images/categories/adventure.jpg",
        "Horror":"/static/images/categories/horror.jpg",
        "Non-Fiction": "/static/images/categories/fiction.jpg",
        "Thriller": "/static/images/categories/thriller.jpg",
    
    

        # Add more categories if needed
    }

    for cat in categories:
        # Assign image URL or fallback to a default
        cat["image_url"] = category_images.get(
            cat["name"],
            f"https://source.unsplash.com/300x200/?{cat['name'].replace(' ', '')}"
        )

    cursor.close()
    db.close()

    return render_template(
        "reader/reader_dashboard.html",
        username=session.get("username"),
        reader_stats=reader_stats,
        reading_graph_data=reading_graph_data,
        featured_stories=featured_stories,
        categories=categories
    )


# -------------------- Browse Stories --------------------
# -------------------- Browse Stories --------------------
@reader_bp.route('/browse-stories')
def browse_stories():
    if 'user_id' not in session or session.get('user_role') not in ['author', 'reader']:
        return redirect(url_for('auth.login'))

    search_query = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)
    per_page = 9

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    where_clauses = []
    params = []

    # ✅ Include categories join so we can show category_name
    query = '''
        SELECT s.*, 
               u.username AS author_name, 
               u.profile_pic AS author_profile_pic,
               c.name AS category_name
        FROM stories s
        JOIN users u ON s.author_id = u.id
        LEFT JOIN categories c ON s.category_id = c.id
    '''

    # ✅ Readers can only see published stories
    if session.get('user_role') == 'reader':
        where_clauses.append("s.status = 'published'")

    if search_query:
        where_clauses.append("s.title LIKE %s")
        params.append(f"%{search_query}%")

    if category_filter:
        where_clauses.append("s.category_id = %s")
        params.append(category_filter)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY s.created_at DESC LIMIT %s OFFSET %s"
    params.extend([per_page, (page - 1) * per_page])

    cursor.execute(query, params)
    stories = cursor.fetchall()

    # ✅ Fix total count query with the same filters
    count_query = '''
        SELECT COUNT(*) as total 
        FROM stories s
        JOIN users u ON s.author_id = u.id
        LEFT JOIN categories c ON s.category_id = c.id
    '''
    if where_clauses:
        count_query += " WHERE " + " AND ".join(where_clauses)

    cursor.execute(count_query, params[:-2])  # exclude LIMIT/OFFSET
    total = cursor.fetchone()['total']

    # ✅ Fetch categories dynamically
    cursor.execute("SELECT id, name FROM categories ORDER BY name ASC")
    categories = cursor.fetchall()

    cursor.close()
    conn.close()

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "has_prev": page > 1,
        "has_next": page * per_page < total
    }

    return render_template(
        "reader/browse_stories.html",
        stories=stories,
        pagination=pagination,
        categories=categories   # ✅ Pass categories to template
    )



# -------------------- View Story --------------------
@reader_bp.route('/story1/<int:story_id>')
def views_story(story_id):
    if 'user_id' not in session:
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT s.*, u.username as author_name, u.profile_pic as author_profile_pic
        FROM stories s
        JOIN users u ON s.author_id = u.id
        WHERE s.id = %s
    """, (story_id,))
    story = cursor.fetchone()

    if not story:
        cursor.close()
        conn.close()
        return "Story not found", 404

    # Increment views count (global counter)
    cursor.execute("UPDATE stories SET views = views + 1 WHERE id = %s", (story_id,))

    # Get comments
    cursor.execute("""
        SELECT c.*, u.username, u.profile_pic
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.story_id = %s
        ORDER BY c.created_at DESC
    """, (story_id,))
    comments = cursor.fetchall()

    # Check if user already liked
    cursor.execute("SELECT * FROM likes WHERE user_id = %s AND story_id = %s", (session['user_id'], story_id))
    already_liked = cursor.fetchone() is not None

    conn.commit()
    cursor.close()
    conn.close()

    return render_template("reader/view_story.html", story=story, comments=comments, already_liked=already_liked)


# -------------------- Track Detailed Views --------------------
@reader_bp.route('/story1/<int:story_id>/track_view', methods=['POST'])
def track_story_view(story_id):
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO views (story_id, user_id) VALUES (%s, %s)", (story_id, session['user_id']))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
    return jsonify({"success": True})


# -------------------- Like Story --------------------
@reader_bp.route('/story1/<int:story_id>/like', methods=['POST'])
def like_story(story_id):
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM likes WHERE user_id = %s AND story_id = %s", (session['user_id'], story_id))
        if cursor.fetchone():
            return jsonify({"error": "Already liked"}), 400

        cursor.execute("INSERT INTO likes (user_id, story_id) VALUES (%s, %s)", (session['user_id'], story_id))
        cursor.execute("UPDATE stories SET likes = likes + 1 WHERE id = %s", (story_id,))
        cursor.execute("INSERT INTO user_activity (user_id, activity_type, story_id) VALUES (%s, %s, %s)",
                       (session['user_id'], 'like', story_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
    return jsonify({"success": True})


# -------------------- Comment on Story --------------------
@reader_bp.route('/story1/<int:story_id>/comment', methods=['POST'])
def comment_story(story_id):
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 403

    content = request.form.get("content", "").strip()
    if not content:
        return jsonify({"error": "Empty comment"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO comments (story_id, user_id, content) VALUES (%s, %s, %s)",
                       (story_id, session['user_id'], content))
        cursor.execute("UPDATE stories SET comments = comments + 1 WHERE id = %s", (story_id,))
        cursor.execute("INSERT INTO user_activity (user_id, activity_type, story_id) VALUES (%s, %s, %s)",
                       (session['user_id'], 'comment', story_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    # redirect back to story page (fixed function name)
    return redirect(url_for("reader.views_story", story_id=story_id))


# -------------------- Share Story --------------------
@reader_bp.route('/story1/<int:story_id>/share', methods=['POST'])
def share_story(story_id):
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 403

    platform = request.form.get("platform", "other")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO shares (user_id, story_id, platform) VALUES (%s, %s, %s)",
                       (session['user_id'], story_id, platform))
        cursor.execute("UPDATE stories SET shares = shares + 1 WHERE id = %s", (story_id,))
        cursor.execute("INSERT INTO user_activity (user_id, activity_type, story_id) VALUES (%s, %s, %s)",
                       (session['user_id'], 'share', story_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({"success": True})


# -------------------- Notifications Page --------------------
@reader_bp.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch notifications along with user roles
    cursor.execute("""
        SELECT n.id, n.type, n.message, n.status, n.created_at, u.roles
        FROM notifications n
        JOIN users u ON n.user_id = u.id
        WHERE n.user_id = %s
        ORDER BY n.created_at DESC
    """, (session["user_id"],))
    notifications = cursor.fetchall()

    cursor.close()
    conn.close()

    # Check if user is approved as author
    for note in notifications:
        if note['status'] == 'approved' and note['type'] == 'role_change' and 'author' in (note['roles'] or ''):
            session['user_role'] = 'author'
            flash("Your account has been upgraded to Author!", "success")
            break  # no need to check further

    return render_template("reader/notifications.html", notifications=notifications)



# -------------------- Request Author Role --------------------
@reader_bp.route("/request-author", methods=["POST"])
def request_author_role():
    if "user_id" not in session or session.get("user_role") != "reader":
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if user already has a pending request
        cursor.execute("""
            SELECT id FROM notifications 
            WHERE user_id = %s AND type = 'role_change' AND status = 'pending'
        """, (session["user_id"],))
        existing = cursor.fetchone()

        if existing:
            flash("You already have a pending request.", "warning")
        else:
            cursor.execute("""
                INSERT INTO notifications (user_id, type, message, status)
                VALUES (%s, 'role_change', 'Request to become an Author', 'pending')
            """, (session["user_id"],))
            conn.commit()
            flash("Your request has been sent to the admin.", "success")

    except Exception as e:
        conn.rollback()
        flash("Error submitting request: " + str(e), "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("reader.notifications"))