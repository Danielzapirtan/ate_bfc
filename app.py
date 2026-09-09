#!/usr/bin/env python3
from flask import Flask, request, render_template_string, send_from_directory
import os
import subprocess
import shutil
import tempfile
import re
from pathlib import Path

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
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 KindleUnpack Web Interface</h1>
        <p>Convert AZW3 files to EPUB format using KindleUnpack</p>
        
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label for="bookfile">Select AZW3 file:</label>
                <input type="file" name="bookfile" id="bookfile" accept=".azw3,.mobi" required>
            </div>
            
            <div class="form-group">
                <label for="outdir">Output directory (optional, default: ./converted):</label>
                <input type="text" name="outdir" id="outdir" placeholder="./converted" value="./converted">
            </div>
            
            <input type="submit" value="Convert to EPUB">
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
                <li>Clones the KindleUnpack repository (if not present)</li>
                <li>Uses <code>kindleunpack.py</code> to extract the AZW3 file</li>
                <li>Converts to EPUB format (EPUB version 2)</li>
                <li>Copies the resulting EPUB to your specified output directory</li>
                <li>Cleans up temporary files</li>
            </ol>
        </details>
    </div>
</body>
</html>
'''

# Global variable to store KindleUnpack path
KINDLEUNPACK_PATH = None

def ensure_kindleunpack():
    """Clone KindleUnpack repository if not present"""
    global KINDLEUNPACK_PATH
    
    repo_path = Path('KindleUnpack')
    if not repo_path.exists():
        app.logger.info("Cloning KindleUnpack repository...")
        result = subprocess.run(
            ['git', 'clone', 'https://github.com/kevinhendricks/KindleUnpack.git'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise Exception(f"Failed to clone KindleUnpack: {result.stderr}")
    
    kindleunpack_script = repo_path / 'lib' / 'kindleunpack.py'
    if not kindleunpack_script.exists():
        raise Exception(f"kindleunpack.py not found at {kindleunpack_script}")
    
    # Make it executable
    kindleunpack_script.chmod(0o755)
    KINDLEUNPACK_PATH = str(kindleunpack_script)
    app.logger.info(f"KindleUnpack ready at {KINDLEUNPACK_PATH}")
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
            outdir = request.form.get('outdir', './converted').strip()
            if not outdir:
                outdir = './converted'
            
            # Create output directory
            outdir_path = Path(outdir).resolve()
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
            with tempfile.NamedTemporaryFile(delete=False, suffix='.azw3') as tmp_input:
                file.save(tmp_input.name)
                bookpath = Path(tmp_input.name)
            
            try:
                # Create temporary output directory for KindleUnpack
                temp_outdir = Path(tempfile.mkdtemp())
                
                # Run KindleUnpack
                app.logger.info(f"Converting {bookpath} using KindleUnpack...")
                
                # Create a temporary directory for the unpacked content
                unpack_dir = temp_outdir / 'unpacked'
                unpack_dir.mkdir(parents=True)
                
                cmd = [
                    KINDLEUNPACK_PATH,
                    '--epub_version=2',
                    str(bookpath),
                    str(unpack_dir)
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    raise Exception(f"KindleUnpack failed: {result.stderr}")
                
                # Find the generated EPUB file
                mobi8_dir = unpack_dir / 'mobi8'
                if not mobi8_dir.exists():
                    raise Exception(f"mobi8 directory not found in {unpack_dir}")
                
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
                dest_epub = outdir_path / epub_filename
                shutil.copy2(str(epub_source), str(dest_epub))
                
                app.logger.info(f"Successfully converted to {dest_epub}")
                
                # Determine relative path for download
                relative_path = dest_epub.relative_to(Path.cwd()) if dest_epub.is_relative_to(Path.cwd()) else dest_epub
                
                message = f"✅ Successfully converted!<br>📁 Saved to: <code>{dest_epub}</code>"
                message_type = "success"
                download_path = f"/download/{relative_path}"
                
            finally:
                # Clean up temporary files
                if bookpath.exists():
                    bookpath.unlink()
                if temp_outdir.exists():
                    shutil.rmtree(temp_outdir, ignore_errors=True)
            
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
        file_path = Path(filename)
        if not file_path.exists():
            return "File not found", 404
        
        # Security: ensure file is within current directory
        if not str(file_path.resolve()).startswith(str(Path.cwd().resolve())):
            return "Access denied", 403
        
        directory = str(file_path.parent)
        return send_from_directory(directory, file_path.name, as_attachment=True)
    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        return f"Error downloading file: {str(e)}", 500

if __name__ == '__main__':
    # Initialize KindleUnpack on startup
    try:
        ensure_kindleunpack()
        print("✅ KindleUnpack initialized successfully")
        print("🌐 Starting Flask server at http://localhost:5000")
    except Exception as e:
        print(f"❌ Failed to initialize KindleUnpack: {e}")
        print("Please ensure git is installed and you have internet connection")
        exit(1)
    
    app.run(debug=True, host='0.0.0.0', port=5010)
