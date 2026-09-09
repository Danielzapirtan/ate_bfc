#!/usr/bin/env python3
from flask import Flask, request, render_template_string, send_from_directory
import os
import subprocess
import shutil
import tempfile
import re
from pathlib import Path
import requests
import zipfile
import io

app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>KindleUnpack Web Interface</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; margin-top: 0; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; color: #555; }
        input[type="text"], input[type="file"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }
        input[type="submit"] { background: #4CAF50; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        input[type="submit"]:hover { background: #45a049; }
        .message { margin-top: 20px; padding: 15px; border-radius: 5px; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .download-link { display: inline-block; margin-top: 10px; color: #007bff; text-decoration: none; }
        .download-link:hover { text-decoration: underline; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 5px; border: 1px solid #ddd; overflow-x: auto; }
        .file-input-wrapper { display: flex; gap: 10px; align-items: center; }
        .file-input-wrapper input[type="text"] { flex: 1; }
        .loading { display: none; margin-top: 10px; }
        .loading.active { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 KindleUnpack Web Interface</h1>
        <p>Convert AZW3 files to EPUB format using KindleUnpack</p>
        
        <form method="POST" enctype="multipart/form-data" id="uploadForm">
            <div class="form-group">
                <label for="bookfile">Select AZW3 file:</label>
                <input type="file" name="bookfile" id="bookfile" accept=".azw3,.mobi" required>
            </div>
            
            <div class="form-group">
                <label for="outdir">Output directory (optional, default: ./converted):</label>
                <input type="text" name="outdir" id="outdir" placeholder="./converted" value="./converted">
            </div>
            
            <input type="submit" value="Convert to EPUB" id="submitBtn">
            <div class="loading" id="loading">⏳ Processing... Please wait.</div>
        </form>
        
        {% if message %}
        <div class="message {{ message_type }}">
            {{ message|safe }}
            {% if download_path %}
            <br><a href="{{ download_path }}" class="download-link">📥 Download EPUB file</a>
            {% endif %}
        </div>
        {% endif %}
        
        <hr>
        <details>
            <summary><strong>How it works</strong></summary>
            <p>This tool:</p>
            <ol>
                <li>Downloads KindleUnpack from GitHub (if not present)</li>
                <li>Uses <code>kindleunpack.py</code> to extract the AZW3 file</li>
                <li>Converts to EPUB format (EPUB version 2)</li>
                <li>Copies the resulting EPUB to your specified output directory</li>
                <li>Cleans up temporary files</li>
            </ol>
        </details>
    </div>
    
    <script>
        document.getElementById('uploadForm').addEventListener('submit', function() {
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').value = 'Processing...';
            document.getElementById('loading').classList.add('active');
        });
    </script>
</body>
</html>
'''

# Global variable to store KindleUnpack path
KINDLEUNPACK_PATH = None

def download_kindleunpack():
    """Download KindleUnpack from GitHub as ZIP"""
    repo_path = Path('/tmp/KindleUnpack')
    
    if repo_path.exists():
        # Check if kindleunpack.py exists
        kindleunpack_script = repo_path / 'lib' / 'kindleunpack.py'
        if kindleunpack_script.exists():
            app.logger.info("KindleUnpack already exists")
            return str(kindleunpack_script)
        else:
            # Remove incomplete directory
            shutil.rmtree(repo_path)
    
    app.logger.info("Downloading KindleUnpack from GitHub...")
    
    # Download the ZIP archive
    zip_url = "https://github.com/kevinhendricks/KindleUnpack/archive/refs/heads/master.zip"
    
    try:
        response = requests.get(zip_url, timeout=30)
        response.raise_for_status()
        
        # Extract ZIP
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            # Extract to a temporary directory first
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_ref.extractall(temp_dir)
                
                # Find the extracted directory (should be KindleUnpack-master)
                extracted_dirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
                if not extracted_dirs:
                    raise Exception("No directory found in ZIP")
                
                source_dir = extracted_dirs[0]
                
                # Move to final location
                if repo_path.exists():
                    shutil.rmtree(repo_path)
                shutil.move(str(source_dir), str(repo_path))
        
        kindleunpack_script = repo_path / 'lib' / 'kindleunpack.py'
        if not kindleunpack_script.exists():
            raise Exception(f"kindleunpack.py not found after extraction")
        
        # Make it executable
        kindleunpack_script.chmod(0o755)
        
        app.logger.info(f"KindleUnpack downloaded successfully at {kindleunpack_script}")
        return str(kindleunpack_script)
        
    except Exception as e:
        app.logger.error(f"Failed to download KindleUnpack: {str(e)}")
        raise Exception(f"Failed to download KindleUnpack: {str(e)}")

def ensure_kindleunpack():
    """Ensure KindleUnpack is available"""
    global KINDLEUNPACK_PATH
    
    if KINDLEUNPACK_PATH is None:
        KINDLEUNPACK_PATH = download_kindleunpack()
    
    return KINDLEUNPACK_PATH

@app.route('/', methods=['GET', 'POST'])
def index():
    message = None
    message_type = None
    download_path = None
    
    try:
        ensure_kindleunpack()
    except Exception as e:
        return render_template_string(
            HTML_TEMPLATE,
            message=f"Error initializing KindleUnpack: {str(e)}",
            message_type="error",
            download_path=None
        )
    
    if request.method == 'POST':
        try:
            # Get output directory
            outdir = request.form.get('outdir', '/tmp/converted').strip()
            if not outdir:
                outdir = '/tmp/converted'
            
            # Create output directory
            outdir_path = Path(outdir)
            if not outdir_path.is_absolute():
                outdir_path = Path.cwd() / outdir_path
            outdir_path = outdir_path.resolve()
            outdir_path.mkdir(parents=True, exist_ok=True)
            
            # Handle file upload
            if 'bookfile' not in request.files:
                return render_template_string(
                    HTML_TEMPLATE,
                    message="No file uploaded",
                    message_type="error",
                    download_path=None
                )
            
            file = request.files['bookfile']
            if file.filename == '':
                return render_template_string(
                    HTML_TEMPLATE,
                    message="No file selected",
                    message_type="error",
                    download_path=None
                )
            
            # Check file extension
            if not file.filename.lower().endswith(('.azw3', '.mobi')):
                return render_template_string(
                    HTML_TEMPLATE,
                    message="Please upload an AZW3 or MOBI file",
                    message_type="error",
                    download_path=None
                )
            
            # Save uploaded file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix='.azw3', dir='/tmp') as tmp_input:
                file.save(tmp_input.name)
                bookpath = Path(tmp_input.name)
            
            try:
                # Create temporary output directory for KindleUnpack
                temp_outdir = Path(tempfile.mkdtemp(dir='/tmp'))
                
                # Run KindleUnpack
                app.logger.info(f"Converting {bookpath} using KindleUnpack...")
                
                # Create a temporary directory for the unpacked content
                unpack_dir = temp_outdir / 'unpacked'
                unpack_dir.mkdir(parents=True)
                
                cmd = [
                    'python3',
                    KINDLEUNPACK_PATH,
                    '--epub_version=2',
                    str(bookpath),
                    str(unpack_dir)
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode != 0:
                    raise Exception(f"KindleUnpack failed: {result.stderr}")
                
                # Find the generated EPUB file
                mobi8_dir = unpack_dir / 'mobi8'
                if not mobi8_dir.exists():
                    # Try to find EPUB in the unpacked directory
                    epub_files = list(unpack_dir.rglob('*.epub'))
                    if not epub_files:
                        raise Exception(f"No EPUB file found in {unpack_dir}")
                    epub_source = epub_files[0]
                else:
                    # Find the EPUB file (it should have the same name as input but with .epub)
                    epub_filename = Path(file.filename).stem + '.epub'
                    epub_source = mobi8_dir / epub_filename
                    
                    if not epub_source.exists():
                        # Try to find any .epub file in mobi8 directory
                        epub_files = list(mobi8_dir.glob('*.epub'))
                        if not epub_files:
                            raise Exception(f"No EPUB file found in {mobi8_dir}")
                        epub_source = epub_files[0]
                        epub_filename = epub_source.name
                
                # Copy to output directory
                dest_epub = outdir_path / epub_source.name
                shutil.copy2(str(epub_source), str(dest_epub))
                
                app.logger.info(f"Successfully converted to {dest_epub}")
                
                # Determine download path
                download_path = f"/download/{dest_epub.name}"
                
                message = f"✅ Successfully converted!<br>📁 Saved to: <code>{dest_epub}</code>"
                message_type = "success"
                
            finally:
                # Clean up temporary files
                if bookpath.exists():
                    bookpath.unlink()
                if temp_outdir.exists():
                    shutil.rmtree(temp_outdir, ignore_errors=True)
            
        except subprocess.TimeoutExpired:
            message = "❌ Error: Conversion timed out after 5 minutes"
            message_type = "error"
            download_path = None
        except Exception as e:
            app.logger.error(f"Conversion error: {str(e)}")
            message = f"❌ Error: {str(e)}"
            message_type = "error"
            download_path = None
    
    return render_template_string(
        HTML_TEMPLATE,
        message=message,
        message_type=message_type,
        download_path=download_path
    )

@app.route('/download/<path:filename>')
def download_file(filename):
    """Serve the converted EPUB file"""
    try:
        # Get the output directory from the request or use default
        outdir = request.args.get('dir', '/tmp/converted')
        outdir_path = Path(outdir)
        if not outdir_path.is_absolute():
            outdir_path = Path.cwd() / outdir_path
        outdir_path = outdir_path.resolve()
        
        file_path = outdir_path / Path(filename).name
        if not file_path.exists():
            return "File not found", 404
        
        directory = str(file_path.parent)
        return send_from_directory(directory, file_path.name, as_attachment=True)
    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        return f"Error downloading file: {str(e)}", 500

if __name__ == '__main__':
    # Install requests if not present
    try:
        import requests
    except ImportError:
        print("Installing requests...")
        subprocess.check_call(['pip', 'install', 'requests'])
    
    # Initialize KindleUnpack on startup
    try:
        ensure_kindleunpack()
        print("✅ KindleUnpack initialized successfully")
        print("🌐 Starting Flask server at http://localhost:5000")
    except Exception as e:
        print(f"❌ Failed to initialize KindleUnpack: {e}")
        print("Please ensure you have internet connection")
        exit(1)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
