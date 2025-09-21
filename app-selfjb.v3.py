from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import tempfile

app = Flask(__name__)
CORS(app)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

@app.route('/')
def index():
    return send_file('index-selfjb.v3.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not file.filename.endswith('.jsonl'):
        return jsonify({'error': 'File must be a JSONL file'}), 400

    try:
        # Save the uploaded file temporarily
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.jsonl') as tmp_file:
            content = file.read().decode('utf-8')
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        # Process the JSONL file - extract all entries with 'cot_sentences' and 'selfjb_annos'
        entries = []
        with open(tmp_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if 'cot_sentences' in data and 'selfjb_annos' in data:
                            # Parse sentences and check for self-jailbreaking annotations
                            sentences = []
                            cot_sentences = data['cot_sentences'].strip()
                            selfjb_indices = set(data['selfjb_annos'].get('answer', []))

                            if cot_sentences:
                                # Split by sentence separators and extract sentence text
                                sentence_lines = cot_sentences.split('\n')
                                for line in sentence_lines:
                                    if line.strip() and ' - ' in line:
                                        parts = line.split(' - ', 1)
                                        if len(parts) == 2:
                                            sentence_id_str = parts[0].strip().replace('sentence ', '')
                                            try:
                                                sentence_id = int(sentence_id_str)
                                                sentence_text = parts[1].strip()
                                                is_selfjb = sentence_id in selfjb_indices
                                                sentences.append({
                                                    'id': sentence_id,
                                                    'text': sentence_text,
                                                    'is_selfjb': is_selfjb,
                                                    'corrected_selfjb': is_selfjb  # Initially same as original
                                                })
                                            except ValueError:
                                                # Skip if sentence ID is not a valid integer
                                                continue

                            entries.append({
                                'raw_prompt': data.get('raw_prompt', ''),
                                'sentences': sentences,
                                'final_answer': data.get('final_answer', ''),
                                'original': data  # Store the full object in case needed
                            })
                    except json.JSONDecodeError:
                        continue

        # Clean up temporary file
        os.unlink(tmp_file_path)

        return jsonify({
            'entries': entries,
            'total': len(entries)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save_corrections', methods=['POST'])
def save_corrections():
    try:
        data = request.get_json()
        entry_index = data.get('entry_index')
        corrections = data.get('corrections', [])

        # In a real application, you would save these corrections to a database
        # For now, we'll just return success
        return jsonify({'success': True, 'saved_corrections': len(corrections)}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/export_corrected', methods=['POST'])
def export_corrected():
    try:
        data = request.get_json()
        entries = data.get('entries', [])

        # Create corrected JSONL content
        corrected_lines = []
        for entry in entries:
            # Get the corrected self-jailbreaking sentence indices
            corrected_selfjb_indices = []
            for sentence in entry.get('sentences', []):
                if sentence.get('corrected_selfjb', False):
                    corrected_selfjb_indices.append(sentence['id'])

            # Update the original entry with corrected annotations
            original = entry.get('original', {})
            original['selfjb_annos'] = {'answer': corrected_selfjb_indices}
            corrected_lines.append(json.dumps(original, ensure_ascii=False))

        corrected_content = '\n'.join(corrected_lines)

        # Save to temporary file and return
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl', encoding='utf-8') as tmp_file:
            tmp_file.write(corrected_content)
            tmp_file_path = tmp_file.name

        return send_file(tmp_file_path, as_attachment=True, download_name='corrected_annotations.jsonl')

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=7101)