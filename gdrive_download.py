import os
import sys
import argparse
import re
import json
import time
import threading
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

class ProgressTracker:
    def __init__(self, total_files: int, quiet: bool = False, no_progress: bool = False):
        self.total_files = total_files
        self.completed_files = 0
        self.current_file = ""
        self.current_file_size = 0
        self.current_downloaded = 0
        self.start_time = time.time()
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self.quiet = quiet
        self.no_progress = no_progress
        self.lock = threading.Lock()
        
    def update_file(self, filename: str, file_size: int = 0):
        with self.lock:
            self.current_file = filename
            self.current_file_size = max(0, file_size)  # Ensure non-negative
            self.current_downloaded = 0
            if file_size > 0:
                self.total_bytes += file_size
    
    def update_progress(self, downloaded: int):
        with self.lock:
            # Only update if downloaded amount makes sense
            if downloaded >= 0 and downloaded <= self.current_file_size:
                old_downloaded = self.current_downloaded
                self.current_downloaded = downloaded
                # Only add positive progress
                if downloaded > old_downloaded:
                    self.downloaded_bytes += (downloaded - old_downloaded)
    
    def complete_file(self):
        with self.lock:
            self.completed_files += 1
            # Don't print "Completed" message to avoid interference with progress display
    
    def get_speed(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed > 1:  # Avoid division by very small numbers
            return self.downloaded_bytes / elapsed
        return 0
    
    def get_eta(self) -> str:
        speed = self.get_speed()
        if speed > 0 and self.total_bytes > 0:
            remaining_bytes = max(0, self.total_bytes - self.downloaded_bytes)
            eta_seconds = remaining_bytes / speed
            
            if eta_seconds < 0:
                return "0s"
            elif eta_seconds < 60:
                return f"{eta_seconds:.0f}s"
            elif eta_seconds < 3600:
                return f"{eta_seconds/60:.0f}m {eta_seconds%60:.0f}s"
            else:
                hours = eta_seconds // 3600
                minutes = (eta_seconds % 3600) // 60
                return f"{hours:.0f}h {minutes:.0f}m"
        return "--"
    
    def format_size(self, bytes_val: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f}TB"
    
    def display_progress(self):
        if self.quiet or self.no_progress:
            return
            
        with self.lock:
            if self.total_files == 0:
                return
            
            # Current file progress - only show if file size is known
            current_percent = 0
            if self.current_file_size > 0 and self.current_downloaded <= self.current_file_size:
                current_percent = min(100.0, (self.current_downloaded / self.current_file_size) * 100)
            
            # Speed and ETA
            speed = self.get_speed()
            eta = self.get_eta()
            
            # Create progress line without progress bar
            if self.current_file_size > 0:
                # Show file progress
                progress_line = (
                    f"\r{current_percent:5.1f}% "
                    f"({self.completed_files}/{self.total_files}) "
                    f"{self.format_size(speed)}/s "
                    f"ETA: {eta} "
                    f"{self.current_file[:50]}"
                )
            else:
                # Show only file count progress for files with unknown size
                progress_line = (
                    f"\r({self.completed_files}/{self.total_files}) "
                    f"{self.format_size(speed)}/s "
                    f"ETA: {eta} "
                    f"{self.current_file[:60]}"
                )
            
            # Clear line and print progress
            print(progress_line.ljust(100), end='', flush=True)

class GDrive:
    def __init__(self):
        self.config_dir = Path.home() / '.gdrive'
        self.config_file = self.config_dir / 'config.json'
        self.service = None
        self.progress_tracker = None
        
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

    def count_files_and_size(self, folder_id: str, recursive: bool) -> tuple[int, int]:
        count = 0
        total_size = 0
        items = self.get_folder_items(folder_id)
        
        for item in items:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                if recursive:
                    sub_count, sub_size = self.count_files_and_size(item['id'], recursive)
                    count += sub_count
                    total_size += sub_size
            else:
                count += 1
                # Safely handle file size
                try:
                    file_size = int(item.get('size', 0)) if item.get('size') else 0
                    total_size += max(0, file_size)  # Ensure non-negative
                except (ValueError, TypeError):
                    # Skip if size is not a valid number
                    pass
        
        return count, total_size

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
            
            # Get file size for progress tracking
            try:
                file_info = self.service.files().get(fileId=file_id, fields="size").execute()
                file_size = int(file_info.get('size', 0)) if file_info.get('size') else 0
            except:
                file_size = 0
            
            # Update progress tracker
            if self.progress_tracker:
                self.progress_tracker.update_file(file_name, file_size)
            
            # Create temporary file path
            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
            
            # If target file already exists, remove it (Windows requirement)
            if file_path.exists():
                file_path.unlink()
            
            # Download to temporary file with progress tracking
            with open(temp_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                    if status and self.progress_tracker and file_size > 0:
                        # Calculate downloaded bytes more safely
                        progress_ratio = min(1.0, max(0.0, status.resumable_progress))
                        downloaded = int(progress_ratio * file_size)
                        self.progress_tracker.update_progress(downloaded)
                        self.progress_tracker.display_progress()
            
            # Rename temp file to final name
            temp_path.rename(file_path)
            
            if self.progress_tracker:
                self.progress_tracker.complete_file()
                # Clear progress line and show completion
                if not self.progress_tracker.quiet:
                    print(f"\r{' ' * 100}\r{file_name}", flush=True)
            
            return True
            
        except Exception as e:
            # Clean up temp file if it exists
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass  # Ignore cleanup errors
            
            if 'File not found' in str(e):
                return False
            else:
                if not (self.progress_tracker and self.progress_tracker.quiet):
                    print(f"\nFailed to download {file_name}: {e}")
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
                self.download_file(item['id'], name, item['mimeType'], file_path)

    def get_file_info(self, file_id: str) -> Optional[Dict]:
        try:
            return self.service.files().get(fileId=file_id, fields="id, name, mimeType, size").execute()
        except:
            return None

    def cp(self, source: str, destination: str, recursive: bool = False, quiet: bool = False, no_progress: bool = False) -> None:
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
            # Folder - count files first for progress tracking
            if not quiet:
                print("Scanning folder structure...")
            
            total_files, total_size = self.count_files_and_size(item_id, recursive)
            
            if total_files == 0:
                print("No files to copy")
                return
            
            # Initialize progress tracker
            self.progress_tracker = ProgressTracker(total_files, quiet, no_progress)
            
            if not quiet:
                print(f"Found {total_files} files ({self.progress_tracker.format_size(total_size)})")
                print("Starting download...")
            
            self.cp_folder(item_id, local_path, recursive)
            
        else:
            # Single file
            self.progress_tracker = ProgressTracker(1, quiet, no_progress)
            
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
            
            self.download_file(item_id, output_file, item_info['mimeType'], output_dir)
        
        # Final summary
        if self.progress_tracker and not quiet:
            elapsed_time = time.time() - self.progress_tracker.start_time
            avg_speed = self.progress_tracker.get_speed()
            
            print(f"\n\nDownload completed!")
            print(f"Files: {self.progress_tracker.completed_files}/{self.progress_tracker.total_files}")
            print(f"Total size: {self.progress_tracker.format_size(self.progress_tracker.downloaded_bytes)}")
            print(f"Time elapsed: {elapsed_time:.1f}s")
            print(f"Average speed: {self.progress_tracker.format_size(avg_speed)}/s")

def main():
    parser = argparse.ArgumentParser(
        prog='gdrive',
        description='Google Drive command line tool with progress display'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Configure command
    subparsers.add_parser('configure', help='Configure authentication')
    
    # List command
    ls_parser = subparsers.add_parser('ls', help='List files and folders')
    ls_parser.add_argument('path', nargs='?', help='Folder ID or URL')
    
    # Copy command
    cp_parser = subparsers.add_parser('cp', help='Copy files/folders from Drive')
    cp_parser.add_argument('source', help='Drive folder ID or URL')
    cp_parser.add_argument('destination', help='Local directory')
    cp_parser.add_argument('-r', '--recursive', action='store_true', 
                          help='Copy folders recursively')
    cp_parser.add_argument('--quiet', action='store_true', 
                          help='Suppress all output except errors')
    cp_parser.add_argument('--no-progress', action='store_true', 
                          help='Disable progress display but show completion messages')
    cp_parser.add_argument('--progress', action='store_true', 
                          help='Force enable progress display (default)')
    
    args = parser.parse_args()
    
    gdrive = GDrive()
    
    if args.command == 'configure':
        gdrive.configure()
    elif args.command == 'ls':
        gdrive.ls(args.path)
    elif args.command == 'cp':
        # Handle conflicting options
        quiet = args.quiet
        no_progress = args.no_progress
        if args.progress:
            no_progress = False
        
        gdrive.cp(args.source, args.destination, args.recursive, quiet, no_progress)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()