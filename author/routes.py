from flask import Blueprint, render_template, session, redirect, url_for, request, flash, current_app, jsonify
from utils import get_author_stats, get_db_connection
import os
from werkzeug.utils import secure_filename
from datetime import datetime

author_bp = Blueprint('author', __name__)

# Allowed extensions for image uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@author_bp.route('/dashboard')
def author_dashboard():
    if 'user_id' not in session or session.get('user_role') != 'author':
        flash("You need to be an author to access this page.", "warning")
        return redirect(url_for('auth.login'))
    
    stats = get_author_stats(session['user_id'])
    
    # Get author's recent stories
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
            SELECT * FROM stories 
            WHERE author_id = %s 
            ORDER BY created_at DESC 
            LIMIT 5
        ''', (session['user_id'],))
        author_stories = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching author stories: {e}")
        author_stories = []
    finally:
        cursor.close()
        conn.close()
    
    return render_template(
        'author/author_dashboard.html', 
        stats=stats, 
        username=session['username'],
        author_stories=author_stories
    )





@author_bp.route('/create_story', methods=['GET', 'POST'])
def create_story():
    if 'user_id' not in session or session['user_role'] != 'author':
        return redirect(url_for('auth.login'))
    
    error = None
    story_id = request.args.get('id')  # 🔹 Allow edit via ?id=123

    # Fetch categories from database dynamically
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name FROM categories ORDER BY name ASC")
    categories = [row['name'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        status = request.form.get('status')
        category = request.form.get('category')
        tags = request.form.get('tags')
        action = request.form.get('action')
        publish_date = request.form.get('publish_date')

        # Handle file upload
        featured_image = None
        if 'featured_image' in request.files:
            file = request.files['featured_image']
            if file and file.filename != '' and allowed_file(file.filename):
                try:
                    upload_folder = os.path.join(current_app.static_folder, "uploads")
                    os.makedirs(upload_folder, exist_ok=True)

                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    unique_filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(upload_folder, unique_filename)
                    file.save(file_path)

                    # Store relative path
                    featured_image = f"uploads/{unique_filename}"

                except Exception as e:
                    error = f"Error uploading image: {str(e)}"
            elif file and file.filename != '':
                error = "Invalid file type. Please upload PNG, JPG, JPEG, or GIF images."

        # Handle preview
        if action == 'preview':
            session['preview_title'] = title
            session['preview_content'] = content
            session['preview_category'] = category
            session['preview_tags'] = tags
            session['preview_status'] = status
            session['preview_schedule_date'] = publish_date
            session['preview_featured_image'] = featured_image
            session['preview_story_id'] = story_id  # 🔹 store story id for editing

            return redirect(url_for('author.preview_story'))

        # Validation
        if not title or not content:
            error = 'Title and content are required'
        else:
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                if story_id:  
                    # 🔹 UPDATE existing story
                    update_query = """
                        UPDATE stories 
                        SET title=%s, content=%s, status=%s, category=%s, publish_date=%s
                        WHERE id=%s AND author_id=%s
                    """
                    cursor.execute(update_query, (
                        title, content, status, category,
                        publish_date if status == 'scheduled' else datetime.now() if status == 'published' else None,
                        story_id, session['user_id']
                    ))

                    # Only update image if new one uploaded
                    if featured_image:
                        cursor.execute(
                            "UPDATE stories SET featured_image=%s WHERE id=%s AND author_id=%s",
                            (featured_image, story_id, session['user_id'])
                        )

                else:  
                    # 🔹 INSERT new story
                    insert_query = """
                        INSERT INTO stories (title, content, author_id, status, category, featured_image, publish_date) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (
                        title, content, session['user_id'], status, category, featured_image,
                        publish_date if status == 'scheduled' else datetime.now() if status == 'published' else None
                    ))

                conn.commit()

                flash('Story saved successfully!' if status != 'published' else 'Story published successfully!', 'success')
                return redirect(url_for('author.my_stories'))

            except Exception as e:
                conn.rollback()
                error = f'Error creating/updating story: {str(e)}'

            finally:
                cursor.close()
                conn.close()

    return render_template(
        'author/create_story.html',
        error=error,
        username=session['username'],
        categories=categories,           # ✅ Pass dynamic categories
        selected_category=None,          # ✅ Optional, can preselect when editing
        clear_storage=True
    )




@author_bp.route('/my_stories')
def my_stories():
    if 'user_id' not in session or session['user_role'] != 'author':
        return redirect(url_for('auth.login'))
    
    # Get author's stories from database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT * FROM stories 
        WHERE author_id = %s 
        ORDER BY created_at DESC
    ''', (session['user_id'],))
    
    stories = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('author/my_stories.html', stories=stories, username=session['username'])



from decimal import Decimal

@author_bp.route('/performance')
def performance():
    if 'user_id' not in session or session['user_role'] != 'author':
        return redirect(url_for('auth.login'))
    
    stats = get_author_stats(session['user_id']) or {}

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ✅ Top 5 stories
    cursor.execute('''
        SELECT * FROM stories 
        WHERE author_id = %s 
        ORDER BY views DESC, likes DESC, comments DESC 
        LIMIT 5
    ''', (session['user_id'],))
    top_stories = cursor.fetchall()

    # ✅ All stories
    cursor.execute('''
        SELECT * FROM stories 
        WHERE author_id = %s 
        ORDER BY created_at DESC
    ''', (session['user_id'],))
    all_stories = cursor.fetchall()

    # ✅ Category distribution
    cursor.execute('''
        SELECT category, COUNT(*) as count
        FROM stories 
        WHERE author_id = %s AND category IS NOT NULL
        GROUP BY category
    ''', (session['user_id'],))
    category_data = cursor.fetchall()

    cursor.close()
    conn.close()

    # ✅ Convert Decimal → int safely
    def safe_int(value):
        if value is None:
            return 0
        if isinstance(value, Decimal):
            return int(value)
        return int(value)

    total_views = safe_int(stats.get("total_views"))
    total_likes = safe_int(stats.get("total_likes"))
    total_comments = safe_int(stats.get("total_comments"))
    total_shares = safe_int(stats.get("total_shares"))

    # ✅ Engagement Metrics
    avg_time = round((total_likes + total_comments) / max(total_views, 1) * 3, 2)  # minutes
    completion_rate = round((total_likes + total_comments + total_shares) / max(total_views, 1) * 100, 2)
    bounce_rate = max(0, 100 - completion_rate)
    engagement_score = round(((total_likes*0.3 + total_comments*0.3 + total_shares*0.2 + total_views*0.2) / max(total_views, 1)) * 100, 2)

    metrics = {
        "avg_time": avg_time,
        "completion_rate": completion_rate,
        "bounce_rate": bounce_rate,
        "engagement_score": engagement_score
    }

    return render_template(
        "author/performance.html", 
        stats={
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares
        },
        top_stories=top_stories,
        stories=all_stories,
        category_data=category_data,
        metrics=metrics,
        username=session['username']
    )





@author_bp.route('/story/<int:story_id>')
def view_story(story_id):
    if 'user_id' not in session or session['user_role'] != 'author':
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get the story (only if author owns it)
    cursor.execute('''
        SELECT * FROM stories 
        WHERE id = %s AND author_id = %s
    ''', (story_id, session['user_id']))
    
    story = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not story:
        flash('Story not found or access denied', 'error')
        return redirect(url_for('author.my_stories'))
    
    return render_template('author/view.html', story=story, username=session['username'])



@author_bp.route('/story/<int:story_id>/edit')
def edit_story(story_id):
    if 'user_id' not in session or session['user_role'] != 'author':
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get the story (only if author owns it)
    cursor.execute('''
        SELECT * FROM stories 
        WHERE id = %s AND author_id = %s
    ''', (story_id, session['user_id']))
    
    story = cursor.fetchone()
    
    # Format publish_date for datetime-local input
    if story and story.get('publish_date'):
        story['formatted_publish_date'] = story['publish_date'].strftime('%Y-%m-%dT%H:%M')
    else:
        story['formatted_publish_date'] = ''
    
    # Fetch categories dynamically from the database
    cursor.execute('SELECT name FROM categories ORDER BY name ASC')
    categories = [row['name'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    if not story:
        flash('Story not found or access denied', 'error')
        return redirect(url_for('author.my_stories'))
    
    return render_template(
        'author/edit_story.html',
        story=story,
        username=session['username'],
        categories=categories  # ✅ Pass dynamic categories
    )




@author_bp.route('/story/<int:story_id>/delete', methods=['POST'])
def delete_story(story_id):
    if 'user_id' not in session or session['user_role'] != 'author':
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Delete the story (only if author owns it)
        cursor.execute('''
            DELETE FROM stories 
            WHERE id = %s AND author_id = %s
        ''', (story_id, session['user_id']))
        
        conn.commit()
        
        if cursor.rowcount > 0:
            flash('Story deleted successfully', 'success')
        else:
            flash('Story not found or access denied', 'error')
            
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting story: {str(e)}', 'error')
        
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('author.my_stories'))


@author_bp.route('/browse-stories')
def browse_stories():
    # --- Check authentication & role ---
    if 'user_id' not in session or session.get('user_role') != 'author':
        return redirect(url_for('auth.login'))

    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 8  # Changed to match the JavaScript storiesPerPage value
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ---------------- Base query ----------------
    query = '''
        SELECT s.*, u.username AS author_name, u.profile_pic AS author_profile_pic,
               c.name AS category_name
        FROM stories s 
        JOIN users u ON s.author_id = u.id
        LEFT JOIN categories c ON s.category_id = c.id
    '''
    where_clauses = []
    params = []

    # ---------------- Author-specific rule ----------------
    # Show: (own stories of ANY status) OR (others' stories that are published)
    where_clauses.append("(s.author_id = %s OR s.status = 'published')")
    params.append(user_id)

    # ---------------- Search filter ----------------
    if search_query:
        where_clauses.append("""
            (s.title LIKE %s OR s.content LIKE %s OR u.username LIKE %s OR s.tags LIKE %s)
        """)
        like_pattern = f"%{search_query}%"
        params.extend([like_pattern, like_pattern, like_pattern, like_pattern])

    # ---------------- Category filter ----------------
    if category_filter:
        where_clauses.append("s.category = %s")
        params.append(category_filter)

    # ---------------- Status filter ----------------
    if status_filter:
        # Apply status only to author's own stories
        where_clauses.append("(s.author_id = %s AND s.status = %s)")
        params.extend([user_id, status_filter])

    # ---------------- Build final query ----------------
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY s.created_at DESC LIMIT %s OFFSET %s"
    params.extend([per_page, (page - 1) * per_page])

    cursor.execute(query, params)
    stories = cursor.fetchall()

    # ---------------- Count total ----------------
    count_query = '''
        SELECT COUNT(*) as total 
        FROM stories s 
        JOIN users u ON s.author_id = u.id
        LEFT JOIN categories c ON s.category = c.id
    '''
    count_params = []
    
    # Rebuild where clauses for count query without the status special handling
    count_where_clauses = ["(s.author_id = %s OR s.status = 'published')"]
    count_params.append(user_id)
    
    if search_query:
        count_where_clauses.append("""
            (s.title LIKE %s OR s.content LIKE %s OR u.username LIKE %s OR s.tags LIKE %s)
        """)
        like_pattern = f"%{search_query}%"
        count_params.extend([like_pattern, like_pattern, like_pattern, like_pattern])
    
    if category_filter:
        count_where_clauses.append("s.category = %s")
        count_params.append(category_filter)
    
    if status_filter:
        count_where_clauses.append("(s.author_id = %s AND s.status = %s)")
        count_params.extend([user_id, status_filter])
    
    if count_where_clauses:
        count_query += " WHERE " + " AND ".join(count_where_clauses)

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()['total']

    # ---------------- Fetch categories ----------------
    cursor.execute("SELECT id, name FROM categories ORDER BY name ASC")
    categories = cursor.fetchall()

    cursor.close()
    conn.close()

    # ---------------- Pagination ----------------
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "has_prev": page > 1,
        "has_next": page * per_page < total
    }

    return render_template(
        "author/browse_stories.html",
        stories=stories,
        pagination=pagination,
        categories=categories,
        selected_category=category_filter,
        search_query=search_query,
        status_filter=status_filter
    )



@author_bp.route('/story/<int:story_id>/update', methods=['POST'])
def update_story(story_id):
    print(f"\n--- DEBUG: Update story route called for story_id={story_id} ---")

    if 'user_id' not in session or session.get('user_role') != 'author':
        print("DEBUG: User not authenticated or not author")
        return redirect(url_for('auth.login'))

    # Get form values
    title = request.form.get('title')
    content = request.form.get('content')
    status = request.form.get('status')
    category = request.form.get('category')
    action = request.form.get('action')
    publish_date = request.form.get('publish_date')
    remove_image = request.form.get('remove_image')

    print(f"DEBUG: Form values → title={title}, content_length={len(content) if content else 0}, status={status}, action={action}, publish_date={publish_date}, remove_image={remove_image}")

    # DB connection
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Verify story ownership
        cursor.execute("SELECT * FROM stories WHERE id=%s AND author_id=%s", (story_id, session['user_id']))
        story = cursor.fetchone()
        if not story:
            flash("Story not found or access denied", "error")
            return redirect(url_for("author.my_stories"))

        featured_image = story['featured_image']

        # Handle file upload
        if 'featured_image' in request.files:
            file = request.files['featured_image']
            if file and file.filename and allowed_file(file.filename):
                upload_folder = os.path.join(current_app.static_folder, "uploads")
                os.makedirs(upload_folder, exist_ok=True)
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_filename = f"{timestamp}_{filename}"
                file_path = os.path.join(upload_folder, unique_filename)
                file.save(file_path)
                featured_image = f"uploads/{unique_filename}"

        # Remove image if requested
        if remove_image == "1":
            featured_image = None

        # Determine final status
        if action == "save_draft":
            final_status = "draft"
        elif action == "publish":
            final_status = "published"
        elif action == "update":
            final_status = status
        else:
            final_status = status  # fallback

        # Determine final publish date
        final_publish_date = story['publish_date']
        if final_status == "scheduled" and publish_date:
            try:
                final_publish_date = datetime.strptime(publish_date, "%Y-%m-%dT%H:%M")
            except ValueError:
                flash("Invalid date format", "error")
                return redirect(url_for("author.edit_story", story_id=story_id))
        elif final_status == "published" and not story['publish_date']:
            final_publish_date = datetime.now()
        elif final_status == "draft":
            final_publish_date = None

        # Validation
        if not title or not content or not content.strip():
            flash("Title and content are required", "error")
            return redirect(url_for("author.edit_story", story_id=story_id))

        # Update story in DB
        update_query = """
            UPDATE stories
            SET title=%s, content=%s, status=%s, category=%s,
                featured_image=%s, publish_date=%s, updated_at=NOW()
            WHERE id=%s AND author_id=%s
        """
        update_params = (title, content, final_status, category, featured_image, final_publish_date, story_id, session['user_id'])
        cursor.execute(update_query, update_params)
        conn.commit()
        flash("Story updated successfully!", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Error updating story: {e}", "error")
    finally:
        cursor.close()
        conn.close()

    # Redirect based on action
    if action == "save_draft":
        return redirect(url_for("author.edit_story", story_id=story_id))
    else:
        return redirect(url_for("author.view_story", story_id=story_id))






# -------------------- View Story --------------------
@author_bp.route('/story1/<int:story_id>')
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

    return render_template("author/view_story.html", story=story, comments=comments, already_liked=already_liked)


# -------------------- Track Detailed Views --------------------
@author_bp.route('/story1/<int:story_id>/track_view', methods=['POST'])
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
@author_bp.route('/story1/<int:story_id>/like', methods=['POST'])
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
@author_bp.route('/story1/<int:story_id>/comment', methods=['POST'])
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
    return redirect(url_for("author.views_story", story_id=story_id))


# -------------------- Share Story --------------------
@author_bp.route('/story1/<int:story_id>/share', methods=['POST'])
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


# -------------------- Author / User Activity Summary --------------------
@author_bp.route('/my-activity')
def my_activity():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    uid = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            COALESCE(SUM(s.likes),0) AS total_likes_received,
            COALESCE(SUM(s.shares),0) AS total_shares_received,
            COALESCE(SUM(s.comments),0) AS total_comments_received,
            COALESCE(SUM(s.views),0) AS total_views_received
        FROM stories s
        WHERE s.author_id = %s
    """, (uid,))
    totals_received = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS likes_given FROM likes WHERE user_id = %s", (uid,))
    likes_given = cursor.fetchone()['likes_given']

    cursor.execute("SELECT COUNT(*) AS shares_made FROM shares WHERE user_id = %s", (uid,))
    shares_made = cursor.fetchone()['shares_made']

    cursor.execute("SELECT COUNT(*) AS comments_made FROM comments WHERE user_id = %s", (uid,))
    comments_made = cursor.fetchone()['comments_made']

    cursor.execute("SELECT COUNT(*) AS views_made FROM views WHERE user_id = %s", (uid,))
    views_made = cursor.fetchone()['views_made']

    cursor.execute("""
        SELECT ua.*, s.title as story_title
        FROM user_activity ua
        LEFT JOIN stories s ON ua.story_id = s.id
        WHERE ua.user_id = %s
        ORDER BY ua.timestamp DESC
        LIMIT 50
    """, (uid,))
    recent_activity = cursor.fetchall()

    cursor.close()
    conn.close()

    performed = {
        'likes_given': likes_given,
        'shares_made': shares_made,
        'comments_made': comments_made,
        'views_made': views_made
    }

    return render_template('author/my_activity.html',
                           totals_received=totals_received,
                           performed=performed,
                           recent_activity=recent_activity)



# -------------------- Author Notifications --------------------
@author_bp.route('/notifications')
def notifications():
    if 'user_id' not in session or session.get('user_role') != 'author':
        flash("You must be logged in as an Author to view notifications.", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch notifications for author including admin replies
        cursor.execute("""
            SELECT n.*,
                   CASE WHEN n.type='reply' THEN 'Admin' ELSE u.username END AS sender_name
            FROM notifications n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE n.user_id = %s OR n.type IN ('system','role_change','reply')
            ORDER BY n.created_at DESC
        """, (session['user_id'],))
        notifications = cursor.fetchall()

        # Count unread notifications (for badge)
        cursor.execute("""
            SELECT COUNT(*) AS unread_count
            FROM notifications
            WHERE user_id = %s AND status='unread'
        """, (session['user_id'],))
        unread_count = cursor.fetchone()['unread_count']

    finally:
        cursor.close()
        conn.close()

    return render_template("author/notifications.html", notifications=notifications, unread_count=unread_count)


# -------------------- Author Sends Message to Admin --------------------
@author_bp.route('/notify-admin', methods=['POST'])
def notify_admin():
    if 'user_id' not in session or session.get('user_role') != 'author':
        flash("You must be logged in as an Author to send a message.", "warning")
        return redirect(url_for('auth.login'))

    message = request.form.get("message", "").strip()
    if not message:
        flash("Message cannot be empty.", "danger")
        return redirect(url_for("author.notifications"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO notifications (user_id, type, message, status)
            VALUES (%s, 'message', %s, 'pending')
        """, (session['user_id'], message))
        conn.commit()
        flash("Your message has been sent to the Admin!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error sending message: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("author.notifications"))