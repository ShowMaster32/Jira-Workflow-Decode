# Jira Workflow XML Decoder & Search Tool

## Overview
This tool decodes Base64-encoded content within Jira workflow XML files and provides a powerful search interface to find specific terms across all workflows.

## Features
- **Base64 Decoding**: Automatically detects and decodes Base64-encoded content in XML files
- **Smart Search**: Search across all workflow files for specific terms
- **Interactive Results**: Click on any result to see full details in a modal window
- **Export Functionality**: Export search results to a text file
- **Responsive Design**: Works on desktop and mobile devices

## Prerequisites
- Python 3.6 or higher
- Standard Python libraries (all included in the standard distribution):
  - os, base64, xml.etree.ElementTree, sys, re, gzip, chardet, datetime, json

## Installation
1. Download or clone this repository
2. No additional packages needed - uses only Python standard library

## Directory Structure
```
project-folder/
├── base64_xml_decoder.py   # Main script
├── xml/                    # Input folder (place your XML files here)
├── xml-decoded/            # Output folder (created automatically)
└── result.html            # Search results (created after search)
```

## Usage

### Step 1: Prepare Your Files
1. Create a folder named `xml` in the same directory as the script
2. Place all your Jira workflow XML files in the `xml` folder

### Step 2: Decode XML Files
Run the script without arguments to decode all XML files:
```bash
python base64_xml_decoder.py
```

This will:
- Process all XML files in the `xml` folder
- Decode any Base64-encoded content found
- Save decoded files to `xml-decoded` folder with `-decoded` suffix

### Step 3: Search for Terms
Run the script with a search term:
```bash
python base64_xml_decoder.py 8080
```

Replace `8080` with your search term. The search is case-insensitive.

### Step 4: View Results
Open `result.html` in your web browser to see the search results with:
- Interactive table with truncated content for readability
- Click any row to see full details in a modal
- Export button to save results as text file

## Search Results Interface

### Main Table
The results table shows:
- **Workflow**: Name of the workflow file
- **Transition**: The transition or action name
- **Function ID**: The function or post-function identifier
- **Type**: The argument name (if available) or element type
- **Content**: The content where the search term was found

### Detailed View
Click on any result to see:
- Full file name
- Complete workflow name
- Full transition details
- Complete function ID
- Full content without truncation
- Exact XML path location

### Export Feature
Click the "Export to Text" button to download results as a plain text file.

## Tips & Best Practices

1. **Search Terms**: Use specific terms for better results (e.g., port numbers, URLs, email addresses)

2. **Multiple Searches**: You can run multiple searches - each creates a new result.html file

3. **Large Files**: The tool handles large XML files efficiently by processing them incrementally

4. **Encoding Issues**: The decoder tries multiple encoding formats (UTF-8, Latin-1, Windows-1252) automatically

5. **Viewing Results**: Use a modern browser (Chrome, Firefox, Edge) for best results

## Common Use Cases

- Finding all email configurations containing specific addresses
- Locating webhook URLs or API endpoints
- Finding references to specific servers or ports
- Identifying workflows using certain functions or validators

## Troubleshooting

**No results found**
- Check if the search term exists in the original XML files
- Ensure XML files are in the correct `xml` folder
- Try a broader search term

**Encoding errors**
- The tool automatically tries multiple encodings
- Check the console output for specific error messages

**Can't see result.html**
- Make sure you're opening it in a web browser, not a text editor
- Check that the search completed successfully

## Example
```bash
# Decode all XML files
python base64_xml_decoder.py

# Search for port 8080
python base64_xml_decoder.py 8080

# Search for email addresses
python base64_xml_decoder.py @company.com

# Search for specific function
python base64_xml_decoder.py SendEmail
```

## Output Files

### Decoded XML Files
Located in `xml-decoded/`:
- Original-filename-decoded.xml
- Preserves original XML structure
- Only Base64 content is decoded

### Search Results
`result.html`:
- Interactive web page with search results
- Self-contained (no external dependencies)
- Can be shared with others

## License
This tool is provided as-is for internal use. Modify as needed for your requirements.

## Support
For issues or questions:
1. Check the console output for error messages
2. Verify file permissions and directory structure
3. Ensure Python version compatibility

---
*Version 1.0 - Jira Workflow XML Decoder & Search Tool - Alberto Zini*