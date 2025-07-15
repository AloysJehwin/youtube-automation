from flask import Flask, request, jsonify, send_file, url_for
import uuid
import os
import multiprocessing
from main_generator import generate_video_from_drive  # Must accept 3 args: folder_id, title, output_path
from flask_cors import CORS
from waitress import serve

app = Flask(__name__)
CORS(app)

TASK_FOLDER = "tasks"
os.makedirs(TASK_FOLDER, exist_ok=True)

def generate_video_task(folder_id, title, task_id):
    task_path = os.path.join(TASK_FOLDER, task_id)
    status_file = os.path.join(task_path, "status.txt")
    output_path = os.path.join(task_path, "output.mp4")

    try:
        with open(status_file, "w") as f:
            f.write("processing")

        # Your video generation logic
        generate_video_from_drive(folder_id, title, output_path, task_path)

        with open(status_file, "w") as f:
            f.write("done")

    except Exception as e:
        with open(status_file, "w") as f:
            f.write(f"error: {str(e)}")

@app.route("/start", methods=["POST"])
def start_task():
    data = request.get_json()
    folder_id = data.get("folder_id")
    on_video_title = data.get("on_video_title")

    if not folder_id or not on_video_title:
        return jsonify({"error": "Missing 'folder_id' or 'on_video_title'"}), 400

    task_id = str(uuid.uuid4())
    task_path = os.path.join(TASK_FOLDER, task_id)
    os.makedirs(task_path, exist_ok=True)

    process = multiprocessing.Process(
        target=generate_video_task,
        args=(folder_id, on_video_title, task_id)
    )
    process.start()

    return jsonify({"task_id": task_id, "status": "started"})

@app.route("/status", methods=["POST"])
def check_status():
    data = request.get_json()
    task_id = data.get("task_id")

    if not task_id:
        return jsonify({"error": "Missing 'task_id'"}), 400

    task_path = os.path.join(TASK_FOLDER, task_id)
    status_file = os.path.join(task_path, "status.txt")
    output_file = os.path.join(task_path, "output.mp4")

    if not os.path.exists(status_file):
        return jsonify({"error": "Invalid task_id"}), 404

    with open(status_file, "r") as f:
        status = f.read().strip()

    if status == "done":
        download_url = url_for("download_file", task_id=task_id, _external=True)
        return jsonify({
            "status": "done",
            "task_id": task_id,
            "download_url": download_url
        })
    elif status.startswith("error"):
        return jsonify({"status": "error", "message": status})
    else:
        return jsonify({"task_id": task_id, "status": "processing"})

@app.route("/download/<task_id>", methods=["GET"])
def download_file(task_id):
    task_path = os.path.join(TASK_FOLDER, task_id)
    output_file = os.path.join(task_path, "output.mp4")

    if os.path.exists(output_file):
        return send_file(output_file, as_attachment=True)
    else:
        return jsonify({"status": "error", "message": "File not found"}), 404

if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    serve(app, host='0.0.0.0', port=8000)
