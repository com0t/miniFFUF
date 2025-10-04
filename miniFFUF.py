#!/usr/bin/env python3
import requests
import threading
import time
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
import signal
import itertools
import re
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MiniFFUF:
    def __init__(self, url, wordlists, threads=10, timeout=10, skip_after_placeholder=None, debug=False):
        self.url = url
        self.wordlists = wordlists  # Dict: {placeholder: wordlist_file}
        self.threads = threads
        self.timeout = timeout
        self.session = requests.Session()
        self.results = []
        self.total_requests = 0
        self.completed_requests = 0
        self.start_time = None
        self.running = True
        self.skip_after_placeholder = skip_after_placeholder
        self.found_values = set()
        self.lock = threading.Lock()
        self.debug = debug

        # Thiết lập User-Agent mặc định
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        # Xử lý tín hiệu Ctrl+C
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        print("\n[!] Dừng quá trình fuzzing...")
        self.running = False
        sys.exit(0)

    def load_wordlist_generator(self, wordlist_file):
        """Load wordlist sử dụng generator để tiết kiệm bộ nhớ"""
        try:
            with open(wordlist_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    word = line.strip()
                    if word:
                        yield word
        except FileNotFoundError:
            print(f"[!] Không tìm thấy file wordlist: {wordlist_file}")
            sys.exit(1)
        except Exception as e:
            print(f"[!] Lỗi khi đọc wordlist {wordlist_file}: {e}")
            sys.exit(1)

    def count_lines(self, wordlist_file):
        """Đếm số dòng trong file để tính tổng số requests"""
        try:
            with open(wordlist_file, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def calculate_total_requests(self):
        """Tính tổng số requests sẽ thực hiện"""
        counts = []
        for placeholder, wordlist_file in self.wordlists.items():
            count = self.count_lines(wordlist_file)
            counts.append(count)
            print(f"[+] {placeholder}: {wordlist_file} ({count} words)")

        # Tính tích các số để có tổng combinations
        total = 1
        for count in counts:
            total *= count
        return total

    def replace_placeholders(self, text, replacements):
        """Thay thế placeholders trong text"""
        if not text:
            return text
        result = text
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)
        return result

    def generate_combinations(self):
        """Tạo generator cho tất cả combinations của wordlists"""
        generators = []
        placeholders = []

        for placeholder, wordlist_file in self.wordlists.items():
            generators.append(list(self.load_wordlist_generator(wordlist_file)))
            placeholders.append(placeholder)

        # Tạo cartesian product của tất cả wordlists
        for combination in itertools.product(*generators):
            if not self.running:
                break
            yield dict(zip(placeholders, combination))

    def should_skip_combination(self, replacements):
        """Kiểm tra xem có nên bỏ qua combination này không"""
        if not self.skip_after_placeholder:
            return False

        # Nếu placeholder stop_on có trong replacements và giá trị đã được tìm thấy
        if self.skip_after_placeholder in replacements:
            stop_value = replacements[self.skip_after_placeholder]
            with self.lock:
                if stop_value in self.found_values:
                    return True
        return False

    def add_found_value(self, replacements):
        """Thêm giá trị vào found_values nếu có skip_after_placeholder"""
        if self.skip_after_placeholder and self.skip_after_placeholder in replacements:
            with self.lock:
                self.found_values.add(replacements[self.skip_after_placeholder])

    def debug_print_request(self, method, target_url, headers, data, replacements):
        """In thông tin request khi debug mode"""
        if not self.debug:
            return
        
        print(f"\n{'='*60}")
        print(f"[DEBUG] REQUEST - {self.format_replacements(replacements)}")
        print(f"{'='*60}")
        print(f"Method: {method}")
        print(f"URL: {target_url}")
        
        if headers:
            print("Headers:")
            for key, value in headers.items():
                print(f"  {key}: {value}")
        
        if data:
            print(f"Data: {data}")
        
        print(f"{'='*60}")

    def debug_print_response(self, response, result):
        """In thông tin response khi debug mode"""
        if not self.debug:
            return
        
        print(f"\n{'-'*60}")
        print(f"[DEBUG] RESPONSE")
        print(f"{'-'*60}")
        print(f"Status Code: {response.status_code}")
        print(f"Response Length: {result['length']} bytes")
        print(f"Response Time: {result['response_time']:.2f}s")
        
        print("Response Headers:")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")
        
        # In một phần của response body (giới hạn để tránh spam)
        if hasattr(response, 'content'):
            content_preview = response.content[:500]  # Chỉ in 500 bytes đầu
            try:
                # Thử decode thành text
                text_preview = content_preview.decode('utf-8', errors='ignore')
                print("Response Body (first 500 chars):")
                print(text_preview)
            except:
                print("Response Body (binary content - first 500 bytes):")
                print(content_preview)
        
        print(f"{'-'*60}\n")

    def make_request(self, replacements, method='GET', headers=None, data=None):
        """Thực hiện HTTP request với replacements sử dụng prepared request"""
        target_url = None
        response = None
        try:
            # Thay thế placeholders trong URL
            target_url = self.replace_placeholders(self.url, replacements)

            # Thay thế placeholders trong headers
            req_headers = {}
            if headers:
                for key, value in headers.items():
                    new_key = self.replace_placeholders(key, replacements)
                    new_value = self.replace_placeholders(value, replacements)
                    req_headers[new_key] = new_value

            # Thay thế placeholders trong data
            req_data = None
            if data:
                req_data = self.replace_placeholders(data, replacements)

            # Debug print request
            self.debug_print_request(method, target_url, req_headers, req_data, replacements)

            # Tạo prepared request
            req = requests.Request(
                method=method.upper(),
                url=target_url,
                headers=req_headers,
                data=req_data
            )
            
            # Prepare request
            prepared = self.session.prepare_request(req)
            
            # Đảm bảo URL gốc được giữ nguyên
            prepared.url = target_url
            
            # Gửi prepared request
            response = self.session.send(
                prepared,
                timeout=self.timeout,
                allow_redirects=False,
                verify=False
            )

            # Lưu response body để có thể filter
            try:
                response_text = response.text
            except:
                response_text = response.content.decode('utf-8', errors='ignore')

            result = {
                'replacements': replacements,
                'url': target_url,
                'status_code': response.status_code,
                'length': len(response.content),
                'response_time': response.elapsed.total_seconds(),
                'response_text': response_text,
                'response_object': response  # Lưu response object để debug
            }

            # Debug print response
            self.debug_print_response(response, result)

            return result

        except requests.exceptions.RequestException as e:
            result = {
                'replacements': replacements,
                'url': target_url if target_url else self.url,
                'status_code': 0,
                'length': 0,
                'response_time': 0,
                'response_text': '',
                'error': str(e)
            }
            
            if self.debug:
                print(f"\n[DEBUG] REQUEST ERROR - {self.format_replacements(replacements)}")
                print(f"Error: {str(e)}")
                print(f"URL: {target_url if target_url else self.url}\n")
            
            return result

    def match_response_content(self, response_text, match_text=None, match_regex=None, exclude_text=None, exclude_regex=None):
        """Kiểm tra match/exclude trong response content"""
        if not response_text:
            return False
        
        # Kiểm tra match text (phải có ít nhất một từ match)
        if match_text:
            found_match = False
            for text in match_text:
                if text.lower() in response_text.lower():
                    found_match = True
                    break
            if not found_match:
                return False
        
        # Kiểm tra match regex (phải có ít nhất một regex match)
        if match_regex:
            found_match = False
            for pattern in match_regex:
                try:
                    if re.search(pattern, response_text, re.IGNORECASE | re.MULTILINE):
                        found_match = True
                        break
                except re.error:
                    print(f"[!] Invalid regex pattern: {pattern}")
                    continue
            if not found_match:
                return False
        
        # Kiểm tra exclude text (nếu có bất kỳ từ nào thì loại trừ)
        if exclude_text:
            for text in exclude_text:
                if text.lower() in response_text.lower():
                    return False
        
        # Kiểm tra exclude regex (nếu có bất kỳ regex nào match thì loại trừ)
        if exclude_regex:
            for pattern in exclude_regex:
                try:
                    if re.search(pattern, response_text, re.IGNORECASE | re.MULTILINE):
                        return False
                except re.error:
                    print(f"[!] Invalid regex pattern: {pattern}")
                    continue
        
        return True

    def filter_results(self, result, filter_codes=None, exclude_codes=None, filter_size=None, exclude_size=None, 
                      match_text=None, match_regex=None, exclude_text=None, exclude_regex=None):
        """Lọc kết quả theo status code, size và response content"""
        is_filtered = False
        
        # Logic cũ cho status code và size
        if not filter_codes and not filter_size and not exclude_codes and not exclude_size and not match_text and not match_regex:
            is_filtered = True
        else:
            # Kiểm tra filter status codes
            if filter_codes and result['status_code'] in filter_codes:
                is_filtered = True
            
            # Kiểm tra filter size
            if filter_size and result['length'] in filter_size:
                is_filtered = True
            
            # Kiểm tra exclude status codes
            if exclude_codes and result['status_code'] not in exclude_codes:
                is_filtered = True
            
            # Kiểm tra exclude size
            if exclude_size and result['length'] not in exclude_size:
                is_filtered = True
            
            # Nếu không có filter status/size nào được set, default là true
            if not filter_codes and not filter_size and not exclude_codes and not exclude_size:
                is_filtered = True

        # Kiểm tra response content matching
        if (match_text or match_regex or exclude_text or exclude_regex):
            response_text = result.get('response_text', '')
            content_match = self.match_response_content(response_text, match_text, match_regex, exclude_text, exclude_regex)
            
            # Nếu có filter content thì phải pass cả status/size và content
            if (match_text or match_regex):
                is_filtered = is_filtered and content_match
            else:
                # Chỉ có exclude content thì áp dụng exclude
                is_filtered = is_filtered and content_match

        # Nếu kết quả bị lọc và có skip_after_placeholder, thêm vào found_values
        if is_filtered:
            self.add_found_value(result['replacements'])

        return is_filtered

    def print_progress(self):
        """In tiến trình fuzzing"""
        if not self.debug and self.start_time:  # Không in progress khi debug mode
            elapsed = time.time() - self.start_time
            rps = self.completed_requests / elapsed if elapsed > 0 else 0
            progress = (self.completed_requests / self.total_requests) * 100 if self.total_requests > 0 else 0
            print(f"\r[{self.completed_requests}/{self.total_requests}] "
                  f"Progress: {progress:.1f}% | RPS: {rps:.1f}", end='', flush=True)

    def format_replacements(self, replacements):
        """Format replacements để hiển thị"""
        return " | ".join([f"{k}: {v}" for k, v in replacements.items()])

    def worker(self, replacements, method, headers, data, filter_codes, exclude_codes, filter_size, exclude_size,
              match_text, match_regex, exclude_text, exclude_regex):
        """Worker function cho threading"""
        if not self.running:
            return

        # Kiểm tra xem có nên skip combination này không
        if self.should_skip_combination(replacements):
            with self.lock:
                self.completed_requests += 1
                self.print_progress()
            return

        result = self.make_request(replacements, method, headers, data)

        with self.lock:
            self.completed_requests += 1

        # Lọc kết quả
        if self.filter_results(result, filter_codes, exclude_codes, filter_size, exclude_size,
                              match_text, match_regex, exclude_text, exclude_regex):
            with self.lock:
                self.results.append(result)

            # In kết quả ngay lập tức (không in khi debug mode để tránh spam)
            if not self.debug:
                status_color = self.get_status_color(result['status_code'])
                replacements_str = self.format_replacements(result['replacements'])

                print(f"\n{status_color}[Status: {result['status_code']}] "
                      f"[Size: {result['length']}] "
                      f"[Time: {result['response_time']:.2f}s] "
                      f"[{replacements_str}] "
                      f"-> {result['url']}\033[0m")
            else:
                # Trong debug mode, chỉ in kết quả match một cách đơn giản
                print(f"\n[MATCH] Status: {result['status_code']} | Size: {result['length']} | {self.format_replacements(result['replacements'])} | {result['url']}")
        
        with self.lock:
            self.print_progress()

    def get_status_color(self, status_code):
        """Trả về màu sắc cho status code"""
        if status_code == 200:
            return '\033[92m'  # Green
        elif status_code in [301, 302, 307, 308]:
            return '\033[93m'  # Yellow
        elif status_code in [401, 403]:
            return '\033[91m'  # Red
        elif status_code >= 500:
            return '\033[95m'  # Magenta
        else:
            return '\033[94m'  # Blue

    def run(self, method='GET', headers=None, data=None, filter_codes=None, exclude_codes=None, filter_size=None, exclude_size=None,
           match_text=None, match_regex=None, exclude_text=None, exclude_regex=None):
        """Chạy fuzzing"""
        # Tính tổng số requests
        self.total_requests = self.calculate_total_requests()
        self.start_time = time.time()

        print(f"[+] Target URL: {self.url}")
        print(f"[+] Method: {method}")
        print(f"[+] Threads: {self.threads}")
        print(f"[+] Total combinations: {self.total_requests}")
        print(f"[+] Debug mode: {'ON' if self.debug else 'OFF'}")

        if self.skip_after_placeholder:
            print(f"[+] Skip after placeholder: {self.skip_after_placeholder}")

        if headers:
            print(f"[+] Headers: {headers}")
        if data:
            print(f"[+] Data: {data}")

        # In thông tin filter content
        if match_text:
            print(f"[+] Match text: {match_text}")
        if match_regex:
            print(f"[+] Match regex: {match_regex}")
        if exclude_text:
            print(f"[+] Exclude text: {exclude_text}")
        if exclude_regex:
            print(f"[+] Exclude regex: {exclude_regex}")

        # Kiểm tra placeholders được sử dụng
        self.check_used_placeholders(headers, data)

        print(f"[+] Starting fuzzing...\n")

        try:
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = []
                skipped_count = 0

                for replacements in self.generate_combinations():
                    if not self.running:
                        break

                    # Kiểm tra skip ngay để tránh tạo future không cần thiết
                    if self.should_skip_combination(replacements):
                        skipped_count += 1
                        with self.lock:
                            self.completed_requests += 1
                            self.print_progress()
                        continue

                    future = executor.submit(
                        self.worker, replacements, method, headers, data, filter_codes, exclude_codes, filter_size, exclude_size,
                        match_text, match_regex, exclude_text, exclude_regex
                    )
                    futures.append(future)

                    # Giới hạn futures để tránh tràn bộ nhớ
                    if len(futures) >= self.threads * 2:
                        for i in range(self.threads):
                            if futures and not self.running:
                                break
                            future = futures.pop(0)
                            future.result()

                # Đợi các futures còn lại
                for future in futures:
                    if not self.running:
                        break
                    future.result()

                if skipped_count > 0:
                    print(f"\n[+] Skipped {skipped_count} combinations due to --skip-after")

        except KeyboardInterrupt:
            print("\n[!] Dừng bởi người dùng")
            self.running = False

        # In thống kê cuối
        if self.start_time:
            total_time = time.time() - self.start_time
            print(f"\n\n[+] Fuzzing completed in {total_time:.2f}s")
            print(f"[+] Total requests: {self.completed_requests}")
            print(f"[+] Found results: {len(self.results)}")
            if self.skip_after_placeholder and self.found_values:
                print(f"[+] Found values for {self.skip_after_placeholder}: {sorted(self.found_values)}")

    def check_used_placeholders(self, headers, data):
        """Kiểm tra và hiển thị placeholders được sử dụng"""
        used_placeholders = []

        # Kiểm tra trong URL
        for placeholder in self.wordlists.keys():
            if placeholder in self.url:
                used_placeholders.append(placeholder)

        # Kiểm tra trong headers
        if headers:
            for key, value in headers.items():
                for placeholder in self.wordlists.keys():
                    if placeholder in key or placeholder in value:
                        used_placeholders.append(placeholder)

        # Kiểm tra trong data
        if data:
            for placeholder in self.wordlists.keys():
                if placeholder in data:
                    used_placeholders.append(placeholder)

        print(f"[+] Used placeholders: {list(set(used_placeholders))}")

def parse_wordlist_argument(arg):
    """Parse wordlist argument dạng 'placeholder:file' hoặc chỉ 'file'"""
    if ':' in arg:
        placeholder, wordlist_file = arg.split(':', 1)
        return placeholder, wordlist_file
    else:
        return 'FUZZ', arg

def main():
    parser = argparse.ArgumentParser(description='Mini FFUF - Python Web Fuzzer với Multiple Wordlists')
    parser.add_argument('-u', '--url', required=True, help='Target URL (sử dụng placeholders)')
    parser.add_argument('-w', '--wordlist', action='append', required=True,
                       help='Wordlist (format: "PLACEHOLDER:file" hoặc "file" cho FUZZ)')
    parser.add_argument('-t', '--threads', type=int, default=10, help='Số threads (default: 10)')
    parser.add_argument('-timeout', type=int, default=10, help='Timeout cho request (default: 10s)')
    parser.add_argument('-X', '--method', default='GET', help='HTTP method (default: GET)')
    parser.add_argument('-H', '--headers', action='append', help='HTTP headers (format: "Key: Value")')
    parser.add_argument('-d', '--data', help='POST data (sử dụng placeholders)')
    parser.add_argument('--skip-after', help='Skip combinations với placeholder này sau khi match filter')
    parser.add_argument('-fc', '--filter-codes', help='Lọc status codes (VD: 404,500)')
    parser.add_argument('-ec', '--exclude-codes', help='Loại trừ status codes (VD: 404,500)')
    parser.add_argument('-fs', '--filter-size', help='Lọc response size (VD: 1234,5678)')
    parser.add_argument('-es', '--exclude-size', help='Loại trừ response size (VD: 1234,5678)')
    parser.add_argument('--debug', action='store_true', help='Bật debug mode để in chi tiết request/response')
    
    # Response content filtering options
    parser.add_argument('-mt', '--match-text', help='Match text trong response (phân cách bằng dấu phẩy)')
    parser.add_argument('-mr', '--match-regex', help='Match regex pattern trong response (phân cách bằng dấu phẩy)')
    parser.add_argument('-et', '--exclude-text', help='Exclude text trong response (phân cách bằng dấu phẩy)')
    parser.add_argument('-er', '--exclude-regex', help='Exclude regex pattern trong response (phân cách bằng dấu phẩy)')

    args = parser.parse_args()

    # Parse wordlists
    wordlists = {}
    for wordlist_arg in args.wordlist:
        placeholder, wordlist_file = parse_wordlist_argument(wordlist_arg)
        wordlists[placeholder] = wordlist_file

    # Kiểm tra xem có ít nhất một placeholder được sử dụng
    all_text = args.url
    if args.headers:
        for header in args.headers:
            all_text += ' ' + header
    if args.data:
        all_text += ' ' + args.data

    used_placeholders = [p for p in wordlists.keys() if p in all_text]
    if not used_placeholders:
        print(f"[!] Không tìm thấy placeholder nào trong URL, headers, hoặc data")
        print(f"[!] Placeholders có sẵn: {list(wordlists.keys())}")
        sys.exit(1)

    # Xử lý headers
    headers = {}
    if args.headers:
        for header in args.headers:
            if ':' in header:
                key, value = header.split(':', 1)
                headers[key.strip()] = value.strip()

    # Xử lý filter codes
    filter_codes = None
    if args.filter_codes:
        filter_codes = [int(code.strip()) for code in args.filter_codes.split(',')]

    exclude_codes = None
    if args.exclude_codes:
        exclude_codes = [int(code.strip()) for code in args.exclude_codes.split(',')]

    # Xử lý filter size
    filter_size = None
    if args.filter_size:
        filter_size = [int(size.strip()) for size in args.filter_size.split(',')]

    exclude_size = None
    if args.exclude_size:
        exclude_size = [int(size.strip()) for size in args.exclude_size.split(',')]

    # Xử lý response content filters
    match_text = None
    if args.match_text:
        match_text = [text.strip() for text in args.match_text.split(',')]

    match_regex = None
    if args.match_regex:
        match_regex = [pattern.strip() for pattern in args.match_regex.split(',')]

    exclude_text = None
    if args.exclude_text:
        exclude_text = [text.strip() for text in args.exclude_text.split(',')]

    exclude_regex = None
    if args.exclude_regex:
        exclude_regex = [pattern.strip() for pattern in args.exclude_regex.split(',')]

    # Kiểm tra skip-after placeholder
    skip_after_placeholder = args.skip_after
    if skip_after_placeholder and skip_after_placeholder not in wordlists:
        print(f"[!] Skip-after placeholder '{skip_after_placeholder}' không tồn tại trong wordlists")
        print(f"[!] Placeholders có sẵn: {list(wordlists.keys())}")
        sys.exit(1)

    # Tạo và chạy fuzzer
    fuzzer = MiniFFUF(args.url, wordlists, args.threads, args.timeout, skip_after_placeholder, args.debug)
    fuzzer.run(
        method=args.method,
        headers=headers if headers else None,
        data=args.data,
        filter_codes=filter_codes,
        exclude_codes=exclude_codes,
        filter_size=filter_size,
        exclude_size=exclude_size,
        match_text=match_text,
        match_regex=match_regex,
        exclude_text=exclude_text,
        exclude_regex=exclude_regex
    )

if __name__ == '__main__':
    main()
