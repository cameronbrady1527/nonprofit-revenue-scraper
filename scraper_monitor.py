#!/usr/bin/env python3
"""
Real-time GUI Monitor for Nonprofit Scraper
Shows live statistics and logs in a windowed interface
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import time
import json
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Any, Optional
import logging


@dataclass
class ScraperStats:
    """Container for scraper statistics"""
    total_orgs: int = 0
    completed_orgs: int = 0
    api_count: int = 0
    pdf_count: int = 0
    na_count: int = 0
    rate_limit_count: int = 0
    error_count: int = 0
    current_query: str = ""
    elapsed_time: float = 0.0
    start_time: Optional[datetime] = None
    state_name: str = ""
    parsing_method: str = ""
    
    @property
    def progress_percent(self) -> float:
        if self.total_orgs == 0:
            return 0.0
        return (self.completed_orgs / self.total_orgs) * 100
    
    @property
    def avg_time_per_org(self) -> float:
        if self.completed_orgs == 0:
            return 0.0
        return self.elapsed_time / self.completed_orgs


class ScraperMonitor:
    """Real-time GUI monitor for the nonprofit scraper"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Nonprofit Scraper Monitor")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2b2b2b')
        
        # Data
        self.stats = ScraperStats()
        self.log_queue = queue.Queue()
        self.stats_file = "scraper_stats.json"
        self.logs_file = "scraper_logs.txt"
        
        # Colors
        self.colors = {
            'bg': '#2b2b2b',
            'panel_bg': '#3c3c3c',
            'text': '#ffffff',
            'accent': '#4a9eff',
            'success': '#00ff88',
            'warning': '#ffaa00',
            'error': '#ff4444',
            'api': '#00ddff',
            'ai': '#ff6b6b',
            'na': '#999999'
        }
        
        self.setup_ui()
        self.start_monitoring()
        
    def setup_ui(self):
        """Create the user interface"""
        # Main container
        main_frame = tk.Frame(self.root, bg=self.colors['bg'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top section with two panels side by side
        top_frame = tk.Frame(main_frame, bg=self.colors['bg'])
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Left panel - Progress & Summary
        self.create_progress_panel(top_frame)
        
        # Right panel - Detailed Stats
        self.create_stats_panel(top_frame)
        
        # Bottom section - Logs
        self.create_logs_panel(main_frame)
        
    def create_progress_panel(self, parent):
        """Create the progress and summary panel"""
        panel = tk.LabelFrame(parent, text="Progress & Summary", 
                             bg=self.colors['panel_bg'], fg=self.colors['text'],
                             font=('Arial', 10, 'bold'))
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(panel, variable=self.progress_var, 
                                          maximum=100, style="Custom.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Progress label
        self.progress_label = tk.Label(panel, text="0 / 0 (0.0%)", 
                                     bg=self.colors['panel_bg'], fg=self.colors['text'],
                                     font=('Arial', 12, 'bold'))
        self.progress_label.pack(pady=5)
        
        # State and method info
        self.info_frame = tk.Frame(panel, bg=self.colors['panel_bg'])
        self.info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.state_label = tk.Label(self.info_frame, text="State: Not Started", 
                                  bg=self.colors['panel_bg'], fg=self.colors['accent'],
                                  font=('Arial', 10))
        self.state_label.pack(anchor=tk.W)
        
        self.method_label = tk.Label(self.info_frame, text="Method: Not Started", 
                                   bg=self.colors['panel_bg'], fg=self.colors['accent'],
                                   font=('Arial', 10))
        self.method_label.pack(anchor=tk.W)
        
        # Current activity
        self.activity_label = tk.Label(panel, text="Current: Waiting to start...", 
                                     bg=self.colors['panel_bg'], fg=self.colors['warning'],
                                     font=('Arial', 10), wraplength=350)
        self.activity_label.pack(fill=tk.X, padx=10, pady=5)
        
        # Time info
        self.time_frame = tk.Frame(panel, bg=self.colors['panel_bg'])
        self.time_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.elapsed_label = tk.Label(self.time_frame, text="Elapsed: 0:00:00", 
                                    bg=self.colors['panel_bg'], fg=self.colors['text'],
                                    font=('Arial', 10))
        self.elapsed_label.pack(anchor=tk.W)
        
        self.avg_label = tk.Label(self.time_frame, text="Avg: 0.0s per org", 
                                bg=self.colors['panel_bg'], fg=self.colors['text'],
                                font=('Arial', 10))
        self.avg_label.pack(anchor=tk.W)
        
    def create_stats_panel(self, parent):
        """Create the detailed statistics panel"""
        panel = tk.LabelFrame(parent, text="Detailed Statistics", 
                             bg=self.colors['panel_bg'], fg=self.colors['text'],
                             font=('Arial', 10, 'bold'))
        panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Success stats
        success_frame = tk.Frame(panel, bg=self.colors['panel_bg'])
        success_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(success_frame, text="✅ Data Sources:", 
                bg=self.colors['panel_bg'], fg=self.colors['success'],
                font=('Arial', 10, 'bold')).pack(anchor=tk.W)
        
        self.api_label = tk.Label(success_frame, text="🔢 API: 0", 
                                bg=self.colors['panel_bg'], fg=self.colors['api'],
                                font=('Arial', 10))
        self.api_label.pack(anchor=tk.W, padx=(20, 0))
        
        self.ai_label = tk.Label(success_frame, text="🤖 AI: 0", 
                               bg=self.colors['panel_bg'], fg=self.colors['ai'],
                               font=('Arial', 10))
        self.ai_label.pack(anchor=tk.W, padx=(20, 0))
        
        # Issues stats
        issues_frame = tk.Frame(panel, bg=self.colors['panel_bg'])
        issues_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(issues_frame, text="⚠️ Issues:", 
                bg=self.colors['panel_bg'], fg=self.colors['warning'],
                font=('Arial', 10, 'bold')).pack(anchor=tk.W)
        
        self.rate_limit_label = tk.Label(issues_frame, text="🚫 Rate Limits: 0", 
                                       bg=self.colors['panel_bg'], fg=self.colors['warning'],
                                       font=('Arial', 10))
        self.rate_limit_label.pack(anchor=tk.W, padx=(20, 0))
        
        self.error_label = tk.Label(issues_frame, text="❌ Errors: 0", 
                                  bg=self.colors['panel_bg'], fg=self.colors['error'],
                                  font=('Arial', 10))
        self.error_label.pack(anchor=tk.W, padx=(20, 0))
        
        self.na_label = tk.Label(issues_frame, text="ℹ️ N/A: 0", 
                               bg=self.colors['panel_bg'], fg=self.colors['na'],
                               font=('Arial', 10))
        self.na_label.pack(anchor=tk.W, padx=(20, 0))
        
        # Success rates
        rates_frame = tk.Frame(panel, bg=self.colors['panel_bg'])
        rates_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(rates_frame, text="📊 Success Rates:", 
                bg=self.colors['panel_bg'], fg=self.colors['accent'],
                font=('Arial', 10, 'bold')).pack(anchor=tk.W)
        
        self.success_rate_label = tk.Label(rates_frame, text="Data Retrieved: 0.0%", 
                                         bg=self.colors['panel_bg'], fg=self.colors['success'],
                                         font=('Arial', 10))
        self.success_rate_label.pack(anchor=tk.W, padx=(20, 0))
        
        self.issue_rate_label = tk.Label(rates_frame, text="Issues: 0.0%", 
                                       bg=self.colors['panel_bg'], fg=self.colors['warning'],
                                       font=('Arial', 10))
        self.issue_rate_label.pack(anchor=tk.W, padx=(20, 0))
        
    def create_logs_panel(self, parent):
        """Create the logs panel"""
        panel = tk.LabelFrame(parent, text="Live Logs", 
                             bg=self.colors['panel_bg'], fg=self.colors['text'],
                             font=('Arial', 10, 'bold'))
        panel.pack(fill=tk.BOTH, expand=True)
        
        # Logs text area with scrollbar
        self.logs_text = scrolledtext.ScrolledText(
            panel, 
            bg='#1e1e1e', 
            fg='#ffffff',
            font=('Consolas', 9),
            insertbackground='white',
            wrap=tk.WORD
        )
        self.logs_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configure text tags for colored logs
        self.logs_text.tag_config("INFO", foreground="#00ddff")
        self.logs_text.tag_config("WARNING", foreground="#ffaa00")
        self.logs_text.tag_config("ERROR", foreground="#ff4444")
        self.logs_text.tag_config("SUCCESS", foreground="#00ff88")
        self.logs_text.tag_config("TIMESTAMP", foreground="#888888")
        
    def log(self, message: str, level: str = "INFO"):
        """Add a log message to the display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {level}: {message}\n"
        
        # Add to queue for thread-safe GUI updates
        self.log_queue.put((formatted_message, level))
        
        # Also write to file
        try:
            with open(self.logs_file, "a", encoding="utf-8") as f:
                f.write(formatted_message)
        except Exception:
            pass  # Don't crash if file write fails
    
    def update_stats(self, new_stats: Dict[str, Any]):
        """Update statistics from external data"""
        # Update stats object
        for key, value in new_stats.items():
            if hasattr(self.stats, key):
                setattr(self.stats, key, value)
        
        # Save to file for persistence
        try:
            with open(self.stats_file, "w") as f:
                stats_dict = {
                    'total_orgs': self.stats.total_orgs,
                    'completed_orgs': self.stats.completed_orgs,
                    'api_count': self.stats.api_count,
                    'pdf_count': self.stats.pdf_count,
                    'na_count': self.stats.na_count,
                    'rate_limit_count': self.stats.rate_limit_count,
                    'error_count': self.stats.error_count,
                    'current_query': self.stats.current_query,
                    'elapsed_time': self.stats.elapsed_time,
                    'state_name': self.stats.state_name,
                    'parsing_method': self.stats.parsing_method
                }
                json.dump(stats_dict, f, indent=2)
        except Exception:
            pass  # Don't crash if file write fails
    
    def refresh_display(self):
        """Update the GUI with current statistics"""
        try:
            # Update progress bar and label
            self.progress_var.set(self.stats.progress_percent)
            self.progress_label.config(
                text=f"{self.stats.completed_orgs:,} / {self.stats.total_orgs:,} ({self.stats.progress_percent:.1f}%)"
            )
            
            # Update info labels
            if self.stats.state_name:
                self.state_label.config(text=f"State: {self.stats.state_name}")
            if self.stats.parsing_method:
                self.method_label.config(text=f"Method: {self.stats.parsing_method.upper()}")
            
            # Update current activity
            if self.stats.current_query:
                self.activity_label.config(text=f"Current: Searching '{self.stats.current_query}'")
            
            # Update time labels
            elapsed_str = self.format_time(self.stats.elapsed_time)
            self.elapsed_label.config(text=f"Elapsed: {elapsed_str}")
            self.avg_label.config(text=f"Avg: {self.stats.avg_time_per_org:.2f}s per org")
            
            # Update detailed stats
            self.api_label.config(text=f"🔢 API: {self.stats.api_count:,}")
            self.ai_label.config(text=f"🤖 AI: {self.stats.pdf_count:,}")
            self.rate_limit_label.config(text=f"🚫 Rate Limits: {self.stats.rate_limit_count:,}")
            self.error_label.config(text=f"❌ Errors: {self.stats.error_count:,}")
            self.na_label.config(text=f"ℹ️ N/A: {self.stats.na_count:,}")
            
            # Calculate success rates
            if self.stats.completed_orgs > 0:
                success_count = self.stats.api_count + self.stats.pdf_count
                success_rate = (success_count / self.stats.completed_orgs) * 100
                issue_count = self.stats.rate_limit_count + self.stats.error_count
                issue_rate = (issue_count / self.stats.completed_orgs) * 100
                
                self.success_rate_label.config(text=f"Data Retrieved: {success_rate:.1f}%")
                self.issue_rate_label.config(text=f"Issues: {issue_rate:.1f}%")
            
        except Exception as e:
            self.log(f"Error updating display: {e}", "ERROR")
    
    def process_log_queue(self):
        """Process pending log messages"""
        try:
            while not self.log_queue.empty():
                message, level = self.log_queue.get_nowait()
                
                # Insert message with appropriate color
                self.logs_text.insert(tk.END, message)
                
                # Apply color tags
                if level in ["INFO", "WARNING", "ERROR", "SUCCESS"]:
                    start_line = self.logs_text.index("end-2l linestart")
                    end_line = self.logs_text.index("end-1l lineend")
                    self.logs_text.tag_add(level, start_line, end_line)
                
                # Auto-scroll to bottom
                self.logs_text.see(tk.END)
                
                # Limit log size to prevent memory issues
                lines = int(self.logs_text.index('end-1c').split('.')[0])
                if lines > 1000:
                    self.logs_text.delete("1.0", "100.0")
                    
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error processing logs: {e}")
    
    def monitor_files(self):
        """Monitor stats and logs files for updates"""
        try:
            # Check for stats updates
            if os.path.exists(self.stats_file):
                try:
                    with open(self.stats_file, "r") as f:
                        data = json.load(f)
                        self.update_stats(data)
                except (json.JSONDecodeError, Exception):
                    pass
            
            # Check for new log entries
            if os.path.exists(self.logs_file):
                try:
                    # Simple approach: read last few lines
                    # In a production system, you'd want more sophisticated log tailing
                    pass
                except Exception:
                    pass
                    
        except Exception as e:
            self.log(f"Error monitoring files: {e}", "ERROR")
    
    def start_monitoring(self):
        """Start the monitoring threads"""
        def update_loop():
            while True:
                try:
                    self.monitor_files()
                    self.root.after(0, self.refresh_display)
                    self.root.after(0, self.process_log_queue)
                    time.sleep(1)  # Update every second
                except Exception as e:
                    print(f"Monitor error: {e}")
                    time.sleep(5)
        
        monitor_thread = threading.Thread(target=update_loop, daemon=True)
        monitor_thread.start()
        
        # Initial log
        self.log("Scraper monitor started", "SUCCESS")
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds into HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def run(self):
        """Start the GUI"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.log("Monitor stopped by user", "INFO")
        finally:
            # Cleanup
            try:
                if os.path.exists(self.stats_file):
                    os.remove(self.stats_file)
            except Exception:
                pass


def main():
    """Main function to run the monitor"""
    monitor = ScraperMonitor()
    monitor.run()


if __name__ == "__main__":
    main()