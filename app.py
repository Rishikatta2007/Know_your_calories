from flask import Flask, render_template, request, redirect, flash, session, url_for
from flask_mysqldb import MySQL
import MySQLdb.cursors
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pandas as pd
import numpy as np
import pickle as pk
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("GEMINI_API_KEY")  # make sure your .env contains this

# Flask app setup
app = Flask(__name__)
app.secret_key = 'rishi12345'

# Load model
calorie_model = pk.load(open('calorie_model.pkl', 'rb'))

# MySQL configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'tiger'
app.config['MYSQL_DB'] = 'user_database'
mysql = MySQL(app)

# Email configuration (for feedback)
EMAIL_ADDRESS = 'rishikeshkatta2007@gmail.com'
EMAIL_PASSWORD = '9029615480@Rishi'

# Decorator to require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- MEAL PLANNER ROUTE USING OPENAI ----------
@app.route('/meal_planner', methods=['GET', 'POST'])
@login_required
def meal_planner():
    meal_plan = None

    if request.method == 'POST':
        prompt = (
            f"Create a {request.form['meals']}-meal meal plan for {request.form['calories']} calories per day. "
            f"Preference: {request.form['preference']}. Notes: {request.form['variations']}. "
            f"Include meal names, descriptions, and calorie estimates."
        )

        try:
            response = openai.ChatCompletion.create(
                 model="gpt-3.5-turbo",
                 messages=[{"role": "user", "content": prompt}]
                 )
            meal_plan = response['choices'][0]['message']['content']

            
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

        print(meal_plan)

    return render_template('meal.html', meal_plan=meal_plan)


# Route: Home Page
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/get_started')
def gwtstarted():
    return render_template('signup.html')

@app.route('/main')
def main():
    return render_template('main.html')

# Route: Data Submission and Prediction
@app.route('/submit', methods=['POST'])
@login_required  # Ensure user is logged in before storing data
def submit():
    username = session.get("username")  # Get logged-in username
    
    gender = request.form['gender']
    age = int(request.form['age'])
    exercise = request.form['exercise']
    height = float(request.form['height'])
    weight = float(request.form['weight'])

    # Encode gender and exercise for model compatibility
    gender_encoded = 1 if gender == 'Male' else 0
    exercise_encoded = {'None': 0, 'Moderate': 1, 'Hard': 2}.get(exercise, 0)

    # Prepare input for prediction
    features = np.array([[gender_encoded, age, exercise_encoded, height, weight]])
    prediction = calorie_model.predict(features)[0]

    # Store the user's record in MySQL
    cursor = mysql.connection.cursor()
    cursor.execute(
        "INSERT INTO user_calories (username, age, height, weight, maintenance_calories) VALUES (%s, %s, %s, %s, %s)",
        (username, age, height, weight, prediction)
    )
    mysql.connection.commit()
    cursor.close()

    return render_template(
        'result.html',
        prediction=prediction,
        loss_calories=prediction - 250,
        gain_calories=prediction + 250
    )

@app.route('/previous_data')
@login_required
def previous_data():
    username = session.get("username")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM user_calories WHERE username = %s ORDER BY date DESC", (username,))
    records = cursor.fetchall()
    cursor.close()

    return render_template('previous_data.html', records=records)


@app.route('/zigzag_plan')
def zigzag_plan():
    plan_type = request.args.get('type', 'Maintain')
    base_cal = float(request.args.get('cal', 0))

    def generate_zigzag(cal):
        return [cal + 200, cal - 200, cal, cal + 100, cal - 100, cal + 150, cal - 150]

    week_plan = generate_zigzag(base_cal)

    return render_template('zigzag_plan.html', plan_type=plan_type, week_plan=week_plan)

# Route: Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        cursor.close()
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('main'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
    return render_template('login.html')

# Route: Signup Page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password == confirm_password:
            hashed_password = generate_password_hash(password)
            cursor = mysql.connection.cursor()
            cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)', 
                           (username, hashed_password))
            mysql.connection.commit()
            cursor.close()
            flash('Signup successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Passwords do not match. Please try again.', 'danger')
    return render_template('signup.html')

# Route: Logout
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

@app.route('/nutrition', methods=['GET', 'POST'])
@login_required
def nutrition():
    nutrition_data = None
    food_name = None

    if request.method == 'POST':
        food_name = request.form['food'].strip().lower()
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM food_nutrition WHERE LOWER(food_name) = %s", (food_name,))
        nutrition_data = cursor.fetchone()
        cursor.close()

    return render_template('nutrition.html', nutrition_data=nutrition_data, food_name=food_name)


# Main entry point
if __name__ == '__main__':
    app.run(debug=True)
