from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import cv2
import os
import time
import threading
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Secret key for session management

# Store the footage capture status and course_id for each camera
capturing = {}

# Function to capture frames
def capture_frames(camera_id, course_id):
    if camera_id.isdigit():  # Local camera
        cap = cv2.VideoCapture(int(camera_id))
    else:  # CCTV camera using HTTP
        cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        print(f"Error: Cannot open camera {camera_id}")
        return

    # Create folder for storing frames if not exist
    capture_folder = f"./static/captures/{course_id}"
    if not os.path.exists(capture_folder):
        os.makedirs(capture_folder)

    while capturing.get(camera_id, False):
        ret, frame = cap.read()
        if ret:
            timestamp = int(time.time())
            frame_filename = f"{capture_folder}/{timestamp}.jpg"
            cv2.imwrite(frame_filename, frame)  # Save frame as JPEG
        time.sleep(5)  # Wait for 5 seconds before capturing the next frame

    cap.release()

# Route to render the login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Make a POST request to your Node.js server for login
        url = "http://localhost:3000/api/v1/auth/login"
        payload = {'email': email, 'password': password}
        
        try:
            # Sending POST request to the Node.js login API
            response = requests.post(url, data=payload)

            if response.status_code == 200:
                # Parse the response JSON to get tokens and institute ID
                response_data = response.json()
                print("DATA")
                #print("TEST",response_data)
                access_token = response_data['data']['accessToken']
                refresh_token = response_data['data']['refreshToken']
                institute_id = response_data['data']['institute_id']

                # Store tokens and institute ID in session
                session['access_token'] = access_token
                session['refresh_token'] = refresh_token
                session['institute_id'] = institute_id
                print("INSTITUE ID = ",institute_id)
                # Save user in session as well
                session['user'] = email

                return redirect(url_for('index'))  # Redirect to the index page
            else:
                # If the login fails, show an error message
                return render_template('login.html', error="Invalid email or password")

        except requests.exceptions.RequestException as e:
            # Handle any exceptions that occur during the API call
            return render_template('login.html', error="An error occurred during login")

    return render_template('login.html')

# Route to render the frontend HTML
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))  # Redirect to login if not logged in
    return render_template('index.html')

# API to start capturing frames
@app.route('/start_capture', methods=['POST'])
def start_capture():
    course_id = request.form.get('course_id')
    camera_id = request.form.get('camera_id')

    # Start capturing frames
    if camera_id not in capturing or not capturing[camera_id]:
        capturing[camera_id] = True
        threading.Thread(target=capture_frames, args=(camera_id, course_id)).start()
        return jsonify({"status": "success", "message": "Started capturing frames"})
    else:
        return jsonify({"status": "error", "message": "Already capturing frames"})

# API to stop capturing frames
@app.route('/stop_capture', methods=['POST'])
def stop_capture():
    camera_id = request.form.get('camera_id')
    
    if camera_id in capturing and capturing[camera_id]:
        capturing[camera_id] = False
        return jsonify({"status": "success", "message": "Stopped capturing frames"})
    else:
        return jsonify({"status": "error", "message": "No capture in progress"})

# Function to send frames from a single folder to the backend
import os
import requests
from flask import session  # Assuming you're using Flask session management

def send_folder_to_backend(institute_id, course_id):
    folder_path = f"./static/captures/{course_id}"
    if not os.path.exists(folder_path):
        return {"status": "error", "message": f"No frames found for course ID: {course_id}"}

    # Get all image file paths
    image_paths = [os.path.join(folder_path, file) for file in os.listdir(folder_path) if file.endswith(".jpg")]

    # Prepare the 'files' list for sending multiple files
    files = []
    for image_path in image_paths:
        files.append(('images', (os.path.basename(image_path), open(image_path, 'rb'), 'image/jpeg')))

    # Get the access token from the session
    access_token = session.get('access_token')  # Ensure you have the access token in the session
    institute_id = session.get('institute_id')
    # Check if access token is present
    if not access_token:
        return {"status": "error", "message": "Access token is missing in session"}

    # Define the Express backend endpoint
    url = f"http://localhost:3000/api/v1/images/upload/{institute_id}/{course_id}"

    # Set the headers with the access token
    headers = {
        'Authorization': f'Bearer {access_token}'  # Add the Authorization header
    }

    try:
        # Send a POST request with files and headers
        response = requests.post(url, files=files, headers=headers)

        # Close all file handles
        for file in files:
            file[1][1].close()

        # Handle response
        if response.status_code == 200:
            print(f"DATA SENT SUCCESSFULLY {response}")
            return {"status": "success", "message": "Frames sent successfully"}

        else:
            return {"status": "error", "message": f"Failed to send frames: {response.status_code}", "error": response.text}

    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": "An error occurred while sending frames", "error": str(e)}

# API to send all frames to the Node.js backend
@app.route('/send_frames', methods=['POST'])
def send_frames():
    institute_id = session['institute_id']

    # Directory containing all course folders
    base_folder = "./static/captures"
    if not os.path.exists(base_folder):
        return jsonify({"status": "error", "message": "No folders found"})

    results = []
    for course_id in os.listdir(base_folder):
        folder_path = os.path.join(base_folder, course_id)
        if os.path.isdir(folder_path):  # Ensure it is a directory
            result = send_folder_to_backend(institute_id, course_id)
            results.append({"result": result})

    return jsonify({"results": results})

# API to fetch courses for a specific institute
# API to fetch courses for a specific institute
@app.route('/get_courses', methods=['GET'])
def get_courses():
    if 'access_token' not in session or 'institute_id' not in session:
        return jsonify({"status": "error", "message": "Missing access token or institute ID in session"})

    # Get the institute ID and access token from the session
    institute_id = session['institute_id']
    access_token = session['access_token']

    # Define the API URL
    url = f"http://localhost:3000/api/v1/location/institute/course/{institute_id}"

    # Set the headers with the access token
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    try:
        # Send a GET request with headers
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            print("SUCCESS")
            return jsonify({"status": "success", "courses": response.json()})
        else:
            print("FAILURE")
            return jsonify({"status": "error", "message": f"Failed to fetch courses: {response.status_code}", "error": response.text})

    except requests.exceptions.RequestException as e:
        print("ERROR")
        return jsonify({"status": "error", "message": "An error occurred while fetching courses", "error": str(e)})


if __name__ == "__main__":
    app.run(debug=True) 
