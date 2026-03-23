from flask import current_app as app
from flask import request, jsonify, render_template, send_file
from .ftp_engine import FTPManager
import os
import io

def get_ftp():
    # Extraemos las credenciales desde los headers de cada peticion
    ftp_host = request.headers.get('X-FTP-Host')
    ftp_user = request.headers.get('X-FTP-User')
    ftp_pass = request.headers.get('X-FTP-Pass', '')
    
    if not ftp_host or not ftp_user:
        raise Exception("Faltan credenciales FTP en la peticion.")
        
    ftp = FTPManager(ftp_host, ftp_user, ftp_pass)
    ftp.connect()
    return ftp

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/connect', methods=['POST'])
def connect_test():
    try:
        data = request.json
        ftp = FTPManager(data.get('host'), data.get('user'), data.get('password', ''))
        ftp.connect()
        disks = ftp.list_disks()
        ftp.disconnect()
        return jsonify({"status": "success", "disks": disks})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/list', methods=['POST'])
def api_list_dir():
    try:
        path = request.json.get('path', '')
        ftp = get_ftp()
        items = ftp.list_dir(path)
        ftp.disconnect()
        return jsonify({"status": "success", "items": items})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/read', methods=['POST'])
def api_read_file():
    try:
        path = request.json.get('path')
        ftp = get_ftp()
        file_obj = ftp.download(path)
        ftp.disconnect()
        
        # Archivos que tienen lineas extralargas se parsean usando errors='replace' para no romper
        content = file_obj.read().decode('cp437', errors='replace') # cp437 para sistemas legacy/4690
        return jsonify({"status": "success", "content": content})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/save', methods=['POST'])
def api_save_file():
    try:
        path = request.json.get('path')
        content = request.json.get('content', '')
        
        file_obj = io.BytesIO(content.encode('cp437', errors='replace'))
        
        ftp = get_ftp()
        ftp.upload(file_obj, path)
        ftp.disconnect()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/download', methods=['GET'])
def api_download():
    # Para descargar como adjunto a traves de window.location o target=_blank
    path = request.args.get('path')
    is_dir = request.args.get('is_dir') == 'true'
    
    # Credenciales por query params al no ser ajax puro
    host = request.args.get('host')
    user = request.args.get('user')
    password = request.args.get('pass', '')
    
    try:
        ftp = FTPManager(host, user, password)
        ftp.connect()
        
        if is_dir:
            file_obj = ftp.download_folder_zip(path)
            filename = os.path.basename(path.rstrip('/')) + ".zip"
            mimetype = "application/zip"
        else:
            file_obj = ftp.download(path)
            filename = os.path.basename(path)
            mimetype = "application/octet-stream"
            
        ftp.disconnect()
        return send_file(file_obj, download_name=filename, as_attachment=True, mimetype=mimetype)
    except Exception as e:
        return str(e), 400

@app.route('/api/upload', methods=['POST'])
def api_upload():
    try:
        path = request.form.get('path')
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file part"}), 400
            
        files = request.files.getlist('file')
        ftp = get_ftp()
        
        for file in files:
            if file.filename != '':
                target_path = f"{path.rstrip('/')}/{file.filename}"
                ftp.upload(file.stream, target_path)
                
        ftp.disconnect()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/delete', methods=['POST'])
def api_delete():
    try:
        path = request.json.get('path')
        ftp = get_ftp()
        ftp.delete(path)
        ftp.disconnect()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/rename', methods=['POST'])
def api_rename():
    try:
        old_path = request.json.get('old_path')
        new_path = request.json.get('new_path')
        ftp = get_ftp()
        ftp.rename(old_path, new_path)
        ftp.disconnect()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
