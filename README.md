# Mini FFUF - Python Web Fuzzer

🔍 **Mini FFUF** là một tool fuzzing web được viết bằng Python, lấy cảm hứng từ [FFUF](https://github.com/ffuf/ffuf) nhưng được thiết kế nhỏ gọn và dễ sử dụng.

## ✨ Tính năng

- **Multiple Wordlists**: Hỗ trợ nhiều wordlist với các placeholder khác nhau
- **Multi-threading**: Tăng tốc độ fuzzing với threading
- **Flexible HTTP Methods**: Hỗ trợ GET, POST và các HTTP method khác
- **Custom Headers**: Thêm headers tùy chỉnh cho requests
- **POST Data Support**: Hỗ trợ fuzzing POST data
- **Response Filtering**: Lọc kết quả theo status code và response size  
- **Skip Optimization**: Tối ưu hóa bằng cách skip các combination đã match filter
- **Real-time Progress**: Hiển thị tiến trình và tốc độ fuzzing real-time
- **Colorized Output**: Màu sắc cho status codes để dễ đọc

## 🚀 Cài đặt

```bash
# Clone repository
git clone https://github.com/yourusername/mini-ffuf.git
cd mini-ffuf

# Cài đặt dependencies
pip install requests
```

## 📖 Cách sử dụng

### Cú pháp cơ bản

```bash
python3 miniffuf.py -u <URL> -w <wordlist>
```

### Các tùy chọn

| Option | Mô tả | Ví dụ |
|--------|-------|-------|
| `-u, --url` | Target URL (bắt buộc) | `-u "http://example.com/FUZZ"` |
| `-w, --wordlist` | Wordlist file | `-w "FUZZ:dirs.txt"` hoặc `-w dirs.txt` |
| `-t, --threads` | Số threads (default: 10) | `-t 20` |
| `-timeout` | Timeout cho request (default: 10s) | `-timeout 5` |
| `-X, --method` | HTTP method (default: GET) | `-X POST` |
| `-H, --headers` | HTTP headers | `-H "Cookie: session=abc123"` |
| `-d, --data` | POST data | `-d "username=FUZZ&password=admin"` |
| `--skip-after` | Skip combinations sau khi match filter | `--skip-after PASS` |
| `-fc, --filter-codes` | Lọc status codes | `-fc 404,500` |
| `-fs, --filter-size` | Lọc response size | `-fs 1234,5678` |

### Ví dụ sử dụng

#### 1. Directory Fuzzing cơ bản
```bash
python3 miniffuf.py -u "http://example.com/FUZZ" -w dirs.txt
```

#### 2. Sử dụng multiple wordlists
```bash
python3 miniffuf.py -u "http://example.com/FUZZ/FUZZ2.php" -w "FUZZ:dirs.txt" -w "FUZZ2:files.txt"
```

#### 3. POST Data Fuzzing
```bash
python3 miniffuf.py -u "http://example.com/login" -w "USER:users.txt" -w "PASS:passwords.txt" -X POST -d "username=USER&password=PASS"
```

#### 4. Header Fuzzing
```bash
python3 miniffuf.py -u "http://example.com/" -w "HOST:subdomains.txt" -H "Host: HOST.example.com"
```

#### 5. Với filtering
```bash
python3 miniffuf.py -u "http://example.com/FUZZ" -w dirs.txt -fc 404,403 -fs 1234
```

#### 6. Brute force với skip optimization
```bash
python3 miniffuf.py -u "http://example.com/login" -w "USER:users.txt" -w "PASS:passwords.txt" -X POST -d "username=USER&password=PASS" -fc 401 --skip-after USER
```

## 🔧 Placeholders

Tool hỗ trợ các placeholder tùy chỉnh:

- **FUZZ**: Placeholder mặc định
- **USER, PASS**: Cho brute force login
- **HOST**: Cho subdomain enumeration
- **FILE, DIR**: Cho file/directory discovery
- **Tùy chỉnh**: Bạn có thể tạo placeholder bất kỳ

### Định dạng wordlist

```bash
# Sử dụng FUZZ mặc định
-w wordlist.txt

# Sử dụng placeholder tùy chỉnh
-w "PLACEHOLDER:wordlist.txt"

# Multiple wordlists
-w "USER:users.txt" -w "PASS:passwords.txt"
```

## 📊 Output

Tool hiển thị kết quả real-time với màu sắc:

```
[+] Target URL: http://example.com/FUZZ
[+] Method: GET
[+] Threads: 10
[+] Total combinations: 1000
[+] Starting fuzzing...

[200/1000] Progress: 20.0% | RPS: 15.2
[Status: 200] [Size: 1234] [Time: 0.15s] [FUZZ: admin] -> http://example.com/admin
[Status: 403] [Size: 5678] [Time: 0.12s] [FUZZ: config] -> http://example.com/config
```

### Màu sắc Status Codes

- 🟢 **200**: Xanh lá (thành công)
- 🟡 **3xx**: Vàng (redirect)
- 🔴 **401/403**: Đỏ (unauthorized/forbidden)
- 🟣 **5xx**: Tím (server error)
- 🔵 **Other**: Xanh dương

## ⚡ Tính năng nâng cao

### Skip After Optimization

Khi brute force login, sau khi tìm thấy username hợp lệ, tool có thể skip các combination với username đã tìm thấy:

```bash
python3 miniffuf.py -u "http://example.com/login" -w "USER:users.txt" -w "PASS:passwords.txt" -X POST -d "username=USER&password=PASS" -fc 401 --skip-after USER
```

### Filtering

- **Filter Codes**: Ẩn các status code không mong muốn
- **Filter Size**: Ẩn các response có size cụ thể
- Kết quả được filter sẽ được ghi nhận cho skip optimization

## 🛠️ Yêu cầu hệ thống

- Python 3.6+
- Library: `requests`

## 📝 Ví dụ Wordlists

Tạo các wordlist mẫu:

```bash
# dirs.txt
admin
config
backup
test
uploads

# files.txt
index.php
config.php
backup.sql
test.txt

# users.txt
admin
user
test
guest

# passwords.txt
admin
password
123456
test
```

## 🤝 Đóng góp

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Lưu ý

- Tool này chỉ dành cho mục đích học tập và testing hợp pháp
- Không sử dụng tool để tấn công các hệ thống không được phép
- Hãy tuân thủ các quy định pháp luật khi sử dụng

## 🔗 Liên kết

- [FFUF - Original Tool](https://github.com/ffuf/ffuf)
- [SecLists - Wordlists Collection](https://github.com/danielmiessler/SecLists)

## 📞 Hỗ trợ

Nếu bạn gặp vấn đề hoặc có câu hỏi, hãy tạo issue trên GitHub.

---

**⭐ Nếu tool hữu ích, hãy star repository này!**
