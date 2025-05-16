import os
import base64
import xml.etree.ElementTree as ET
import sys
import re
import gzip
import chardet
from datetime import datetime
import json

def is_base64(s):
    """Check if a string is likely base64 encoded"""
    if isinstance(s, str):
        # Check if string looks like base64 (alphanumeric + /=)
        if re.match(r'^[A-Za-z0-9+/=]+$', s):
            # Additional length check - base64 strings are typically multiples of 4
            if len(s) % 4 == 0:
                try:
                    # Try to decode and catch exceptions
                    base64.b64decode(s, validate=True)
                    return True
                except:
                    return False
    return False

def decode_base64(encoded_string):
    """Decode a base64 string with multiple fallbacks"""
    try:
        decoded_bytes = base64.b64decode(encoded_string)
        
        # First, try to decompress if it's gzipped
        try:
            decompressed = gzip.decompress(decoded_bytes)
            decoded_bytes = decompressed
        except:
            pass  # Not gzipped, use original bytes
        
        # Try to decode as UTF-8
        try:
            return decoded_bytes.decode('utf-8')
        except UnicodeDecodeError:
            pass
        
        # Try to detect encoding
        try:
            result = chardet.detect(decoded_bytes)
            if result['encoding']:
                return decoded_bytes.decode(result['encoding'])
        except:
            pass
        
        # Try common encodings
        encodings = ['latin-1', 'windows-1252', 'iso-8859-1', 'utf-16']
        for encoding in encodings:
            try:
                return decoded_bytes.decode(encoding)
            except:
                continue
        
        # If all else fails, return the original string
        print(f"Warning: Could not decode base64 string, keeping original")
        return encoded_string
        
    except Exception as e:
        print(f"Error decoding base64: {e}")
        return encoded_string

def contains_base64_pattern(text):
    """Check if text contains embedded base64 patterns"""
    # Look for common base64 patterns in Jira XML
    patterns = [
        r'`!`[A-Za-z0-9+/=]+`!`',  # Pattern like `!`base64content`!`
        r'YCFg[A-Za-z0-9+/=]+',    # Pattern starting with YCFg
    ]
    
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False

def extract_and_decode_patterns(text):
    """Extract and decode embedded base64 patterns in text"""
    # Pattern for `!`base64`!`
    pattern1 = r'`!`([A-Za-z0-9+/=]+)`!`'
    
    def replace_pattern1(match):
        encoded = match.group(1)
        decoded = decode_base64(encoded)
        return decoded
    
    text = re.sub(pattern1, replace_pattern1, text)
    
    # Pattern for YCFg followed by base64
    pattern2 = r'YCFg([A-Za-z0-9+/=]+)'
    
    def replace_pattern2(match):
        encoded = match.group(1)
        decoded = decode_base64(encoded)
        return decoded
    
    text = re.sub(pattern2, replace_pattern2, text)
    
    return text

def process_xml_element(elem):
    """Recursively process XML elements and decode base64 values"""
    # Check element text
    if elem.text and elem.text.strip():
        text = elem.text.strip()
        
        # Check for embedded base64 patterns
        if contains_base64_pattern(text):
            elem.text = extract_and_decode_patterns(text)
        # Check if entire text is base64
        elif is_base64(text):
            elem.text = decode_base64(text)
    
    # Check element attributes
    for attr_name, attr_value in elem.attrib.items():
        if contains_base64_pattern(attr_value):
            elem.attrib[attr_name] = extract_and_decode_patterns(attr_value)
        elif is_base64(attr_value):
            elem.attrib[attr_name] = decode_base64(attr_value)
    
    # Recursively process child elements
    for child in elem:
        process_xml_element(child)

def process_xml_file(input_path, output_path):
    """Process a single XML file and decode base64 values"""
    try:
        # Parse XML file
        tree = ET.parse(input_path)
        root = tree.getroot()
        
        # Process all elements
        process_xml_element(root)
        
        # Add "-decoded" to filename
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        output_dir = os.path.dirname(output_path)
        new_output_path = os.path.join(output_dir, f"{base_name}-decoded.xml")
        
        # Write the modified XML to output file
        tree.write(new_output_path, encoding='UTF-8', xml_declaration=True)
        print(f"Processed: {input_path} -> {new_output_path}")
        
        return tree
        
    except Exception as e:
        print(f"Error processing {input_path}: {e}")
        return None

def extract_jira_context_from_path(tree, elem, parent_map, filename):
    """Extract Jira-specific context from XML element using parent map"""
    # Use filename (without extension) as workflow name
    workflow_name = os.path.splitext(os.path.basename(filename))[0]
    
    result = {
        'workflow': workflow_name,
        'transition': 'N/A',
        'function_id': 'N/A',
        'type': elem.attrib.get('name', elem.tag) if elem.tag == 'arg' else elem.tag
    }
    
    # Travel up the tree to find transition, function
    current = elem
    while current is not None:
        tag = current.tag.lower()
        
        # Look for action (which contains transition in Jira)
        if 'action' in tag:
            # Get the transition name from the action
            transition_name = current.get('name')
            if transition_name:
                result['transition'] = transition_name
            # Also check for id
            elif current.get('id'):
                result['transition'] = f"Action-{current.get('id')}"
        
        # Look for function or post-function
        elif any(func_type in tag for func_type in ['function', 'validator', 'condition', 'post-function']):
            # For Jira functions, check various attributes
            func_type = current.get('type') or current.get('class') or current.get('name')
            if func_type:
                result['function_id'] = func_type.split('.')[-1] if '.' in func_type else func_type
            else:
                result['function_id'] = current.tag
        
        # Look for step (which might contain state info)
        elif 'step' in tag:
            step_name = current.get('name')
            if step_name and result['transition'] == 'N/A':
                result['transition'] = f"Step: {step_name}"
        
        # Move up to parent
        current = parent_map.get(current)
    
    return result

def search_in_file(tree, search_term, filename):
    """Search for a term in the decoded XML tree and collect results"""
    search_results = []
    
    def search_element(elem, term, path="", parent_map=None):
        # Build parent map for context extraction
        if parent_map is None:
            parent_map = {c: p for p in tree.iter() for c in p}
        
        current_path = f"{path}/{elem.tag}" if path else elem.tag
        
        # Search in element text
        if elem.text and term.lower() in elem.text.lower():
            context = extract_jira_context_from_path(tree, elem, parent_map, filename)
            context['line'] = current_path
            context['filename'] = os.path.basename(filename)
            # Add the actual content found - just the line containing the search term
            lines = elem.text.strip().split('\n')
            matching_line = ''
            for line in lines:
                if term.lower() in line.lower():
                    matching_line = line.strip()
                    break
            context['content'] = matching_line if matching_line else elem.text.strip()[:100]
            search_results.append(context)
            print(f"  Found in element '{elem.tag}' text: {elem.text[:100]}...")
        
        # Search in attributes
        for attr_name, attr_value in elem.attrib.items():
            if term.lower() in attr_value.lower():
                context = extract_jira_context_from_path(tree, elem, parent_map, filename)
                context['line'] = f"{current_path}/@{attr_name}"
                context['filename'] = os.path.basename(filename)
                # Add the actual content found
                context['content'] = f"{attr_name}=\"{attr_value}\""
                search_results.append(context)
                print(f"  Found in element '{elem.tag}' attribute '{attr_name}': {attr_value[:100]}...")
        
        # Recursively search child elements
        for child in elem:
            search_element(child, term, current_path, parent_map)
    
    if tree:
        root = tree.getroot()
        search_element(root, search_term)
    
    return search_results

def write_results_to_file(search_term, all_results):
    """Write search results to result.html"""
    filename = "./result.html"
    
    with open(filename, 'w', encoding='utf-8') as f:
        # Escape the search term for JavaScript
        js_search_term = search_term.replace("'", "\\'").replace('"', '\\"')
        
        # Write HTML with embedded data
        f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jira Workflow Search Results</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
            overflow-x: auto;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            overflow-x: auto;
        }}
        .search-result {{
            background-color: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow-x: auto;
        }}
        .search-header {{
            background-color: #0052cc;
            color: white;
            padding: 15px;
            border-radius: 8px 8px 0 0;
            margin: -20px -20px 20px -20px;
        }}
        .search-header h2 {{
            margin: 0;
            font-size: 24px;
        }}
        .search-header .timestamp {{
            font-size: 14px;
            opacity: 0.9;
            margin-top: 5px;
        }}
        .table-container {{
            overflow-x: auto;
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            min-width: 800px;
        }}
        th {{
            background-color: #f7f8f9;
            color: #172b4d;
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #dfe1e6;
            font-size: 14px;
        }}
        td {{
            padding: 10px 8px;
            border-bottom: 1px solid #dfe1e6;
            color: #172b4d;
            vertical-align: top;
            font-size: 14px;
        }}
        tr:hover {{
            background-color: #f4f5f7;
        }}
        .file-name {{
            color: #0052cc;
            font-weight: 500;
        }}
        .workflow-name {{
            color: #36b37e;
            font-weight: 500;
        }}
        .transition-name {{
            color: #ff5630;
            font-weight: 500;
        }}
        .function-id {{
            color: #6554c0;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }}
        .type-tag {{
            background-color: #dfe1e6;
            color: #5e6c84;
            padding: 4px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            display: inline-block;
        }}
        .location-path {{
            color: #6b778c;
            font-family: 'Courier New', monospace;
            font-size: 12px;
        }}
        .content-snippet {{
            background-color: #f4f5f7;
            padding: 6px 10px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            color: #091e42;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            cursor: pointer;
        }}
        .truncated {{
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            cursor: pointer;
            display: inline-block;
        }}
        .clickable:hover {{
            text-decoration: underline;
            cursor: pointer;
        }}
        /* Modal styles */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.4);
        }}
        .modal-content {{
            background-color: #fefefe;
            margin: 5% auto;
            padding: 20px;
            border: 1px solid #888;
            width: 90%;
            max-width: 800px;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            max-height: 80vh;
            overflow-y: auto;
        }}
        .close {{
            color: #aaaaaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }}
        .close:hover,
        .close:focus {{
            color: #000;
            text-decoration: none;
        }}
        .modal-header {{
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
            margin-bottom: 20px;
        }}
        .modal-body {{
            margin-bottom: 20px;
        }}
        .detail-row {{
            margin-bottom: 15px;
            display: flex;
            align-items: flex-start;
            flex-wrap: wrap;
        }}
        .detail-label {{
            font-weight: bold;
            color: #172b4d;
            min-width: 120px;
            margin-right: 15px;
            flex-shrink: 0;
        }}
        .detail-value {{
            flex: 1;
            color: #5e6c84;
            word-wrap: break-word;
            word-break: break-all;
            white-space: pre-wrap;
            font-family: 'Courier New', monospace;
            background-color: #f4f5f7;
            padding: 8px;
            border-radius: 4px;
            overflow-wrap: break-word;
            max-width: calc(100% - 135px);
        }}
        .highlight {{
            background-color: #fff3cd;
            color: #856404;
            font-weight: bold;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        .no-results {{
            text-align: center;
            color: #6b778c;
            font-style: italic;
            padding: 40px;
        }}
        .result-count {{
            text-align: right;
            color: #6b778c;
            font-size: 14px;
            margin-top: 20px;
            font-weight: 500;
        }}
        .export-button {{
            background-color: #0052cc;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 20px;
            float: right;
        }}
        .export-button:hover {{
            background-color: #0747a6;
        }}
        .na-value {{
            color: #97a0af;
            font-style: italic;
        }}
        /* Responsive adjustments */
        @media (max-width: 768px) {{
            .modal-content {{
                width: 95%;
                margin: 2% auto;
            }}
            .detail-row {{
                flex-direction: column;
            }}
            .detail-label {{
                margin-bottom: 5px;
            }}
            .detail-value {{
                max-width: 100%;
            }}
            th, td {{
                padding: 8px 4px;
                font-size: 12px;
            }}
            .truncated {{
                max-width: 150px;
            }}
            .content-snippet {{
                max-width: 200px;
            }}
        }}
        @media (max-width: 480px) {{
            .truncated {{
                max-width: 100px;
            }}
            .content-snippet {{
                max-width: 150px;
            }}
            th, td {{
                padding: 6px 2px;
                font-size: 11px;
            }}
        }}
        .highlight {{
            background-color: #fff3cd;
            color: #856404;
            font-weight: bold;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        .no-results {{
            text-align: center;
            color: #6b778c;
            font-style: italic;
            padding: 40px;
        }}
        .result-count {{
            text-align: right;
            color: #6b778c;
            font-size: 14px;
            margin-top: 20px;
            font-weight: 500;
        }}
        .export-button {{
            background-color: #0052cc;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 20px;
            float: right;
        }}
        .export-button:hover {{
            background-color: #0747a6;
        }}
        .na-value {{
            color: #97a0af;
            font-style: italic;
        }}
    </style>
    <script>
        // Store results data globally
        const searchResultsData = {json.dumps(all_results)};
        const searchTerm = "{js_search_term}";
        
        function stripHtml(html) {{
            const tmp = document.createElement("DIV");
            tmp.innerHTML = html;
            return tmp.textContent || tmp.innerText || "";
        }}
        
        function exportToText() {{
            let text = 'JIRA WORKFLOW SEARCH RESULTS\\n';
            text += '========================\\n\\n';
            text += 'Search Term: ' + searchTerm + '\\n';
            text += 'Generated on: ' + new Date().toLocaleString() + '\\n\\n';
            
            searchResultsData.forEach((result, index) => {{
                text += '--- Result ' + (index + 1) + ' ---\\n';
                text += 'File: ' + result.filename + '\\n';
                text += 'Workflow: ' + result.workflow + '\\n';
                text += 'Transition: ' + result.transition + '\\n';
                text += 'Function ID: ' + result.function_id + '\\n';
                text += 'Type: ' + result.type + '\\n';
                text += 'Content: ' + stripHtml(result.content) + '\\n';
                text += 'Location: ' + result.line + '\\n\\n';
            }});
            
            const blob = new Blob([text], {{ type: 'text/plain' }});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'search_results_' + searchTerm.replace(/[^a-z0-9]/gi, '_') + '_' + Date.now() + '.txt';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }}
        
        function truncateText(text, maxLength) {{
            if (text.length <= maxLength) return text;
            return text.substring(0, maxLength) + '...';
        }}
        
        function showDetails(index) {{
            const result = searchResultsData[index];
            const modal = document.getElementById('detailModal');
            const modalContent = document.getElementById('modalDetails');
            
            let contentHtml = `
                <div class="detail-row">
                    <div class="detail-label">File:</div>
                    <div class="detail-value">${{result.filename}}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Workflow:</div>
                    <div class="detail-value">${{result.workflow}}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Transition:</div>
                    <div class="detail-value">${{result.transition}}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Function ID:</div>
                    <div class="detail-value">${{result.function_id}}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Type:</div>
                    <div class="detail-value">${{result.type}}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Content:</div>
                    <div class="detail-value">${{result.content}}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Location:</div>
                    <div class="detail-value">${{result.line}}</div>
                </div>
            `;
            
            modalContent.innerHTML = contentHtml;
            modal.style.display = 'block';
        }}
        
        function closeModal() {{
            const modal = document.getElementById('detailModal');
            modal.style.display = 'none';
        }}
        
        // Close modal when clicking outside
        window.onclick = function(event) {{
            const modal = document.getElementById('detailModal');
            if (event.target == modal) {{
                modal.style.display = 'none';
            }}
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1 style="color: #172b4d; text-align: center; margin-bottom: 30px;">
            <svg style="width: 32px; height: 32px; vertical-align: middle; margin-right: 10px;" viewBox="0 0 24 24" fill="#0052cc">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
            </svg>
            Jira Workflow Search Results
        </h1>
        
        <!-- Modal -->
        <div id="detailModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closeModal()">&times;</span>
                <div class="modal-header">
                    <h2>Result Details</h2>
                </div>
                <div class="modal-body" id="modalDetails">
                    <!-- Details will be inserted here -->
                </div>
            </div>
        </div>
        
        <div class="search-result">
        <div class="search-header">
            <h2>Search Results for: "{search_term}"</h2>
            <div class="timestamp">Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
        </div>
""")
        
        if not all_results:
            f.write(f'        <div class="no-results">No results found for "{search_term}"</div>\n')
        else:
            f.write("""        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="width: 18%;">Workflow</th>
                        <th style="width: 17%;">Transition</th>
                        <th style="width: 17%;">Function ID</th>
                        <th style="width: 10%;">Type</th>
                        <th style="width: 25%;">Content</th>
                    </tr>
                </thead>
                <tbody>
""")
            
            for i, result in enumerate(all_results):
                f.write('                <tr>\n')
                
                # Workflow name
                workflow = result.get('workflow', 'N/A')
                truncated_workflow = workflow[:35] + '...' if len(workflow) > 35 else workflow
                f.write(f'                    <td><span class="workflow-name truncated clickable" onclick="showDetails({i})" title="Click for details">{truncated_workflow}</span></td>\n')
                
                # Transition
                transition = result.get('transition', 'N/A')
                truncated_transition = transition[:25] + '...' if len(transition) > 25 else transition
                if transition != 'N/A':
                    f.write(f'                    <td><span class="transition-name truncated clickable" onclick="showDetails({i})" title="Click for details">{truncated_transition}</span></td>\n')
                else:
                    f.write(f'                    <td><span class="na-value">{transition}</span></td>\n')
                
                # Function ID
                function_id = result.get('function_id', 'N/A')
                truncated_function = function_id[:25] + '...' if len(function_id) > 25 else function_id
                if function_id != 'N/A':
                    f.write(f'                    <td><span class="function-id truncated clickable" onclick="showDetails({i})" title="Click for details">{truncated_function}</span></td>\n')
                else:
                    f.write(f'                    <td><span class="na-value">{function_id}</span></td>\n')
                
                # Type
                type_val = result.get('type', 'N/A')
                f.write(f'                    <td><span class="type-tag">{type_val}</span></td>\n')
                
                # Content
                content = result.get('content', 'N/A')
                if content != 'N/A' and len(content) > 0:
                    # Escape HTML and highlight the search term
                    escaped_content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    truncated_content = escaped_content[:70] + '...' if len(escaped_content) > 70 else escaped_content
                    highlighted_content = truncated_content
                    for variant in [search_term, search_term.lower(), search_term.upper()]:
                        highlighted_content = highlighted_content.replace(variant, f'<span class="highlight">{variant}</span>')
                    
                    f.write(f'                    <td><div class="content-snippet clickable" onclick="showDetails({i})" title="Click for details">{highlighted_content}</div></td>\n')
                else:
                    f.write(f'                    <td><span class="na-value">N/A</span></td>\n')
                
                f.write('                </tr>\n')
            
            f.write("""                </tbody>
            </table>
        </div>
""")
            f.write(f'        <div class="result-count">Total results found: {len(all_results)}</div>\n')
            f.write(f'        <button class="export-button" onclick="exportToText()">Export to Text</button>\n')
        
        f.write("""        </div>
    </div>
</body>
</html>
""")
    
    print(f"\nResults written to {filename}")
    print(f"Open the file in your browser: {os.path.abspath(filename)}")

def clear_output_directory(output_dir):
    """Clear all files in the output directory"""
    if os.path.exists(output_dir):
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    print(f"Deleted: {file_path}")
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
    else:
        os.makedirs(output_dir)

def main():
    # Create and clear output directory
    output_dir = "./xml-decoded"
    clear_output_directory(output_dir)
    
    # Get all XML files from input directory
    input_dir = "./xml"
    xml_files = [f for f in os.listdir(input_dir) if f.endswith('.xml')]
    
    if not xml_files:
        print(f"No XML files found in {input_dir}")
        return
    
    print(f"Found {len(xml_files)} XML files to process.")
    
    # Process each XML file
    decoded_trees = {}
    for xml_file in xml_files:
        input_path = os.path.join(input_dir, xml_file)
        output_path = os.path.join(output_dir, xml_file)
        
        tree = process_xml_file(input_path, output_path)
        if tree:
            decoded_trees[xml_file] = tree
    
    print(f"\nProcessed {len(decoded_trees)} files successfully.")
    
    # Check if search term was provided as command line argument
    if len(sys.argv) > 1:
        search_term = sys.argv[1]
        print(f"\nSearching for '{search_term}'...")
        print("-"*50)
        
        # Search in all decoded files and collect results
        all_results = []
        found_in_files = []
        
        for filename, tree in decoded_trees.items():
            print(f"\nSearching in {filename}:")
            results = search_in_file(tree, search_term, filename)
            if results:
                all_results.extend(results)
                found_in_files.append(filename)
        
        # Write results to file
        write_results_to_file(search_term, all_results)
        
        # Summary
        print(f"\n{'='*50}")
        if found_in_files:
            print(f"Found '{search_term}' in {len(found_in_files)} file(s):")
            for filename in found_in_files:
                print(f"  - {filename}")
        else:
            print(f"'{search_term}' not found in any file.")
    else:
        print("\nNo search term provided. Processing complete.")
        print("To search, run: python base64_xml_decoder.py <search_term>")

if __name__ == "__main__":
    main()