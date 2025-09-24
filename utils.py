import mysql.connector
import hashlib

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'p_2002',
    'database': 'story_creator'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_admin_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM stories")
    total_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM stories WHERE status = 'published'")
    published_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM stories WHERE status = 'scheduled'")
    scheduled_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM stories WHERE status = 'draft'")
    draft_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
    active_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'author'")
    total_authors = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(views), 0) FROM stories")
    total_views = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(likes), 0) FROM stories")
    total_likes = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(comments), 0) FROM stories")
    total_comments = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return {
        'total_stories': total_stories,
        'published_stories': published_stories,
        'scheduled_stories': scheduled_stories,
        'draft_stories': draft_stories,
        'total_users': total_users,
        'active_users': active_users,
        'total_authors': total_authors,
        'total_views': total_views,
        'total_likes': total_likes,
        'total_comments': total_comments
    }

def get_author_stats(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM stories WHERE author_id = %s", (user_id,))
    total_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM stories WHERE author_id = %s AND status = 'published'", (user_id,))
    published_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM stories WHERE author_id = %s AND status = 'scheduled'", (user_id,))
    scheduled_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM stories WHERE author_id = %s AND status = 'draft'", (user_id,))
    draft_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(likes), 0) FROM stories WHERE author_id = %s", (user_id,))
    total_likes = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(comments), 0) FROM stories WHERE author_id = %s", (user_id,))
    total_comments = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(shares), 0) FROM stories WHERE author_id = %s", (user_id,))
    total_shares = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(views), 0) FROM stories WHERE author_id = %s", (user_id,))
    total_views = cursor.fetchone()[0]
    
    # Get top performing stories
    cursor.execute("""
        SELECT title, likes, comments, views, created_at 
        FROM stories 
        WHERE author_id = %s 
        ORDER BY likes DESC 
        LIMIT 3
    """, (user_id,))
    top_stories = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return {
        'total_stories': total_stories,
        'published_stories': published_stories,
        'scheduled_stories': scheduled_stories,
        'draft_stories': draft_stories,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'total_shares': total_shares,
        'total_views': total_views,
        'top_stories': top_stories
    }

def get_admin_recent_activity():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get recent stories
    cursor.execute('''
        SELECT s.*, u.username as author_name 
        FROM stories s 
        JOIN users u ON s.author_id = u.id 
        ORDER BY s.created_at DESC 
        LIMIT 5
    ''')
    recent_stories = cursor.fetchall()
    
    # Get recent user registrations
    cursor.execute('''
        SELECT username, email, created_at, role 
        FROM users 
        ORDER BY created_at DESC 
        LIMIT 5
    ''')
    recent_users = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return {
        'recent_stories': recent_stories,
        'recent_users': recent_users
    }


