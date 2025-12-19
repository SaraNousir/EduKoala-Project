from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import re

app = Flask(__name__)
app.secret_key = 'edukoala_secret_key'  # Needed for session (logging in)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # This lets us access columns by name!
    return conn

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS courses 
                 (id INTEGER PRIMARY KEY, title TEXT, description TEXT, price TEXT, duration TEXT, level TEXT, instructor TEXT)''')

    # NEW: Table to track who bought what
    c.execute('''CREATE TABLE IF NOT EXISTS enrollments 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, course_id INTEGER)''')

    # Add dummy courses
    c.execute('SELECT count(*) FROM courses')
    if c.fetchone()[0] == 0:
        courses = [
            ('Python for Beginners', 'Start your coding journey here. You will learn the basics of Python.', '$49',
             '12 Hours', 'Beginner', 'Dr. Angela Yu'),
            ('Web Development Bootcamp', 'Become a full-stack developer. Covers HTML, CSS, JS.', '$89', '45 Hours',
             'Intermediate', 'Colt Steele'),
            (
            'Data Science 101', 'Analyze data using Pandas and NumPy.', '$99', '20 Hours', 'Advanced', 'Jose Portilla'),
            ('Graphic Design Masterclass', 'Master Photoshop and Illustrator.', '$60', '15 Hours', 'All Levels',
             'Lindsay Marsh')
        ]
        c.executemany(
            "INSERT INTO courses (title, description, price, duration, level, instructor) VALUES (?, ?, ?, ?, ?, ?)",
            courses)
        conn.commit()
    conn.close()

# --- Routes ---
# 1. LANDING PAGE - Everyone can see this
@app.route('/')
def landing():
    return render_template('landing.html')

# 2. LOGIN PAGE (Updated with Error Handling)
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None  # Start with no error
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        # Use a safe query to prevent SQL injection
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user is None:
            error = 'Incorrect username.'
        elif user['password'] != password:
            error = 'Incorrect password.'
        else:
            session['user_id'] = user['id']  # Save user login in session
            session['username'] = user['username']
            return redirect(url_for('dashboard'))

    return render_template('login.html', error=error)

# 3. SIGNUP PAGE (Updated with Validation)
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # --- VALIDATION LOGIC ---
        if ' ' in username:
            error = "Username cannot contain spaces."
        elif len(password) < 6:
            error = "Password must be at least 6 characters long."
        elif not re.search(r"[a-zA-Z]", password):
            error = "Password must contain at least one letter."
        else:
            # If validation passes, check if user already exists
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if user:
                error = 'Username already exists.'
            else:
                # Everything is good, create the user
                conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
                conn.commit()
                conn.close()
                return redirect(url_for('login'))
            conn.close()

    return render_template('signup.html', error=error)


# 4. DASHBOARD (Updated with SEARCH)
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Get the search word from the URL (e.g., ?q=Python)
    search_query = request.args.get('q')

    conn = get_db_connection()
    if search_query:
        # SQL: Find courses that have this word in the title
        # The '%' signs mean "anything before" and "anything after"
        courses = conn.execute('SELECT * FROM courses WHERE title LIKE ?', ('%' + search_query + '%',)).fetchall()
    else:
        # If no search, show all
        courses = conn.execute('SELECT * FROM courses').fetchall()

    conn.close()
    return render_template('dashboard.html', courses=courses, name=session['username'])

# 5. LOGOUT
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('landing'))

# 6. COURSE DETAILS - PROTECTED
@app.route('/course/<int:course_id>')
def course_details(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    conn.close()
    return render_template('course_details.html', course=course)

# 7. ENROLL ROUTE (The Action)
@app.route('/enroll/<int:course_id>')
def enroll(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = get_db_connection()
    # Check if already enrolled to avoid duplicates
    existing = conn.execute('SELECT * FROM enrollments WHERE user_id = ? AND course_id = ?',
                            (user_id, course_id)).fetchone()

    if not existing:
        conn.execute('INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)', (user_id, course_id))
        conn.commit()

    conn.close()
    return redirect(url_for('my_courses', new_enroll=True))  # Send them to My Courses page

# 8. MY COURSES PAGE (The Profile)
@app.route('/my_courses')
def my_courses():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = get_db_connection()
    # This assumes a "JOIN" - Advanced SQL that professors love
    # It grabs only the courses that match the user's ID in the enrollments table
    my_courses = conn.execute('''
        SELECT courses.* FROM courses 
        JOIN enrollments ON courses.id = enrollments.course_id 
        WHERE enrollments.user_id = ?
    ''', (user_id,)).fetchall()
    conn.close()

    # Check if we just enrolled (to show the success message)
    show_success = request.args.get('new_enroll')

    return render_template('my_courses.html', courses=my_courses, show_success=show_success)


# 10. DROP COURSE (The "Delete" part of CRUD)
@app.route('/drop/<int:course_id>')
def drop_course(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = get_db_connection()
    # SQL: Delete the specific enrollment row
    conn.execute('DELETE FROM enrollments WHERE user_id = ? AND course_id = ?', (user_id, course_id))
    conn.commit()
    conn.close()

    return redirect(url_for('my_courses'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)