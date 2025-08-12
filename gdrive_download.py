import os
import sys
import argparse
import re
import json
from pathlib import Path
from typing import List, Dict, Optional

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google.oauth2.service_account import Credentials
    import io
except ImportError:
    print("pip install google-api-python-client google-auth")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class GDrive:
    def __init__(self):
        self.config_dir = Path.home() / '.gdrive'
        self.config_file = self.config_dir / 'config.json'
        self.service = None
        self.downloaded_count = 0
        self.total_count = 0
        
    def configure(self):
        self.config_dir.mkdir(exist_ok=True)
        service_account_path = input("Service account JSON path: ").strip() or './service-account.json'
        config = {
            'auth_type': 'service_account',
            'service_account_path': service_account_path
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f)
        print(f"Config saved to {self.config_file}")

    def load_config(self) -> Dict:
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {'auth_type': 'service_account', 'service_account_path': './service-account.json'}

    def authenticate(self) -> None:
        config = self.load_config()
        service_account_path = config.get('service_account_path', './service-account.json')
        
        if not os.path.exists(service_account_path):
            print(f"Error: {service_account_path} not found")
            print("Run: gdrive configure")
            sys.exit(1)
        
        creds = Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
        self.service = build('drive', 'v3', credentials=creds)

    def extract_id_from_url(self, url: str) -> Optional[str]:
        patterns = [r'/folders/([a-zA-Z0-9-_]+)', r'/file/d/([a-zA-Z0-9-_]+)', r'id=([a-zA-Z0-9-_]+)']
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_folder_items(self, folder_id: str) -> List[Dict]:
        try:
            items = []
            page_token = None
            
            while True:
                results = self.service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                    pageToken=page_token
                ).execute()
                
                items.extend(results.get('files', []))
                page_token = results.get('nextPageToken')
                
                if not page_token:
                    break
            
            return items
        except:
            return []

    def ls(self, path: str = None) -> None:
        self.authenticate()
        
        if path:
            if path.startswith('http'):
                folder_id = self.extract_id_from_url(path)
            else:
                folder_id = path
            
            items = self.get_folder_items(folder_id)
            for item in items:
                prefix = "DIR" if item['mimeType'] == 'application/vnd.google-apps.folder' else "   "
                size = item.get('size', '0') if 'size' in item else '-'
                print(f"{item['modifiedTime'][:10]} {prefix:>3} {size:>10} {item['name']} [{item['mimeType']}]")
        else:
            print("Specify folder ID or URL")

    def count_files(self, folder_id: str, recursive: bool) -> int:
        count = 0
        items = self.get_folder_items(folder_id)
        for item in items:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                if recursive:
                    count += self.count_files(item['id'], recursive)
            else:
                count += 1
        return count

    def sanitize_name(self, name: str) -> str:
        # Remove or replace invalid characters for file systems
        for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
            name = name.replace(char, '_')
        
        # Remove leading/trailing whitespace and multiple consecutive spaces
        name = re.sub(r'\s+', ' ', name.strip())
        
        # Remove trailing dots and spaces (Windows limitation)
        name = name.rstrip('. ')
        
        return name

    def get_shortcut_target(self, file_id: str) -> Optional[Dict]:
        try:
            return self.service.files().get(
                fileId=file_id, 
                fields="shortcutDetails"
            ).execute().get('shortcutDetails', {})
        except:
            return None

    def download_file(self, file_id: str, file_name: str, mime_type: str, output_dir: Path) -> bool:
        temp_path = None
        try:
            # Handle shortcuts
            if mime_type == 'application/vnd.google-apps.shortcut':
                shortcut = self.get_shortcut_target(file_id)
                if shortcut:
                    target_id = shortcut.get('targetId')
                    target_mime = shortcut.get('targetMimeType')
                    if target_id and target_mime:
                        return self.download_file(target_id, file_name, target_mime, output_dir)
                return False
            
            # Handle Google Docs
            if mime_type == 'application/vnd.google-apps.document':
                request = self.service.files().export_media(
                    fileId=file_id, 
                    mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                if not file_name.endswith('.docx'):
                    file_name += '.docx'
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                request = self.service.files().export_media(
                    fileId=file_id, 
                    mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                if not file_name.endswith('.xlsx'):
                    file_name += '.xlsx'
            elif mime_type == 'application/vnd.google-apps.presentation':
                request = self.service.files().export_media(
                    fileId=file_id, 
                    mimeType='application/vnd.openxmlformats-officedocument.presentationml.presentation'
                )
                if not file_name.endswith('.pptx'):
                    file_name += '.pptx'
            else:
                # Regular file
                request = self.service.files().get_media(fileId=file_id)
            
            output_dir.mkdir(parents=True, exist_ok=True)
            file_path = output_dir / file_name
            
            # Create temporary file path
            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
            
            # If target file already exists, remove it (Windows requirement)
            if file_path.exists():
                file_path.unlink()
            
            # Download to temporary file
            with open(temp_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
            
            # Rename temp file to final name
            temp_path.rename(file_path)
            
            self.downloaded_count += 1
            return True
            
        except Exception as e:
            # Clean up temp file if it exists (FIXED)
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass  # Ignore cleanup errors
            
            if 'File not found' in str(e):
                return False
            else:
                print(f"Failed to download {file_name}: {e}")
                return False

    def cp_folder(self, folder_id: str, local_dir: Path, recursive: bool, current_path: str = "") -> None:
        items = self.get_folder_items(folder_id)
        
        for item in items:
            name = self.sanitize_name(item['name'])
            
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                if recursive:
                    sub_path = f"{current_path}/{name}" if current_path else name
                    self.cp_folder(item['id'], local_dir, recursive, sub_path)
            else:
                file_path = local_dir / current_path if current_path else local_dir
                if self.download_file(item['id'], name, item['mimeType'], file_path):
                    print(f"{name}")

    def get_file_info(self, file_id: str) -> Optional[Dict]:
        try:
            return self.service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
        except:
            return None

    def cp(self, source: str, destination: str, recursive: bool = False) -> None:
        self.authenticate()
        
        if source.startswith('http'):
            item_id = self.extract_id_from_url(source)
            if not item_id:
                print("Invalid URL")
                sys.exit(1)
        else:
            item_id = source
        
        local_path = Path(destination)
        
        # Check if it's a file or folder
        item_info = self.get_file_info(item_id)
        if not item_info:
            print("File/folder not found")
            return
        
        if item_info['mimeType'] == 'application/vnd.google-apps.folder':
            # Folder
            self.total_count = self.count_files(item_id, recursive)
            if self.total_count == 0:
                print("No files to copy")
                return
            self.cp_folder(item_id, local_path, recursive)
        else:
            # Single file
            original_name = self.sanitize_name(item_info['name'])
            
            # If destination ends with / or \, treat as directory
            if str(local_path).endswith(('/', '\\')):
                output_dir = local_path
                output_file = original_name
            # If destination exists and is directory, treat as directory
            elif local_path.exists() and local_path.is_dir():
                output_dir = local_path
                output_file = original_name
            # If destination has no extension, treat as directory
            elif '.' not in local_path.name:
                output_dir = local_path
                output_file = original_name
            # Otherwise treat as file path
            else:
                output_dir = local_path.parent
                output_file = local_path.name
            
            if self.download_file(item_id, output_file, item_info['mimeType'], output_dir):
                print(f"{output_file}")

def main():
    parser = argparse.ArgumentParser(prog='gdrive')
    subparsers = parser.add_subparsers(dest='command')
    
    subparsers.add_parser('configure')
    
    ls_parser = subparsers.add_parser('ls')
    ls_parser.add_argument('path', nargs='?', help='Folder ID or URL')
    
    cp_parser = subparsers.add_parser('cp')
    cp_parser.add_argument('source', help='Drive folder ID or URL')
    cp_parser.add_argument('destination', help='Local directory')
    cp_parser.add_argument('-r', '--recursive', action='store_true')
    
    args = parser.parse_args()
    
    gdrive = GDrive()
    
    if args.command == 'configure':
        gdrive.configure()
    elif args.command == 'ls':
        gdrive.ls(args.path)
    elif args.command == 'cp':
        gdrive.cp(args.source, args.destination, args.recursive)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()