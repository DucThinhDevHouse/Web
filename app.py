import pandas as pd
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import re
from datetime import datetime
from flask_mail import Mail, Message  # thêm thư viện mail
import tempfile
from routes.chatbot import init_chatbot_routes

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

init_chatbot_routes(app)

# -------------------------
# ĐƯỜNG DẪN FILE (LINH HOẠT)
# -------------------------
# Nếu user để hotels.csv cùng thư mục với app.py thì dùng file đó,
# nếu không thì fallback sang thư mục data/.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_FOLDER, exist_ok=True)

# ưu tiên file trong cùng thư mục với app.py (nếu tồn tại)
hotels_candidate = os.path.join(BASE_DIR, 'hotels.csv')
if os.path.exists(hotels_candidate):
    HOTELS_CSV = hotels_candidate
else:
    HOTELS_CSV = os.path.join(DATA_FOLDER, 'hotels.csv')

# bookings luôn dùng trong data (nếu bạn muốn khác có thể đổi)
BOOKINGS_CSV = os.path.join(DATA_FOLDER, 'bookings.csv')
REVIEWS_CSV = os.path.join(BASE_DIR, 'reviews.csv') if os.path.exists(os.path.join(BASE_DIR, 'reviews.csv')) else os.path.join(DATA_FOLDER, 'reviews.csv')

# === CẤU HÌNH EMAIL (giữ nguyên) ===
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USE_SSL=False,
    MAIL_USERNAME='hotelpinder@gmail.com',   # Gmail thật
    MAIL_PASSWORD='znsj ynpd burr tdeo',     # Mật khẩu ứng dụng 16 ký tự (giữ như cũ)
    MAIL_DEFAULT_SENDER=('Hotel Pinder', 'hotelpinder@gmail.com')
)
mail = Mail(app)

# === FILE PATHS (Tạo bookings nếu chưa có) ===
try:
    safe_dir = os.path.dirname(BOOKINGS_CSV)
    os.makedirs(safe_dir, exist_ok=True)
    if not os.path.exists(BOOKINGS_CSV):
        df_empty = pd.DataFrame(columns=[
                "hotel_name", "room_type", "price", "user_name", "phone", "email",
                "num_adults", "num_children", "checkin_date", "nights",
                "special_requests", "booking_time", "status"
        ])
        df_empty.to_csv(BOOKINGS_CSV, index=False, encoding="utf-8-sig")
except Exception as e:
    temp_dir = tempfile.gettempdir()
    BOOKINGS_CSV = os.path.join(temp_dir, "bookings.csv")
    print(f"[⚠] Không thể ghi vào thư mục chính, dùng tạm: {BOOKINGS_CSV}")

# === ĐẢM BẢO FILE hotels/reviews (nếu không có thì báo) ===
if not os.path.exists(HOTELS_CSV):
    # nếu không có hotels.csv ở BASE_DIR hoặc data, báo lỗi để user bổ sung
    raise FileNotFoundError(f"❌ Không tìm thấy hotels.csv — đặt file ở: {HOTELS_CSV}")

if not os.path.exists(REVIEWS_CSV):
    pd.DataFrame(columns=["hotel_name", "user", "rating", "comment"]).to_csv(
        REVIEWS_CSV, index=False, encoding="utf-8-sig"
    )

# === HÀM ĐỌC CSV AN TOÀN (sửa để xử lý '5.0', dấu phẩy, v.v.) ===
def read_csv_safe(file_path):
    encodings = ["utf-8-sig", "utf-8", "cp1252"]
    for enc in encodings:
        try:
            # đọc tất cả cột dưới dạng str trước, sau đó convert numeric an toàn
            df = pd.read_csv(file_path, encoding=enc, dtype=str)
            df.columns = df.columns.str.strip()
            # các cột cần convert số
            numeric_cols = ['price', 'stars', 'rating', 'num_adults', 'num_children', 'nights', 'rooms_available']
            for col in numeric_cols:
                if col in df.columns:
                    # loại dấu phẩy, loại ".0" cuối, rồi convert numeric
                    df[col] = df[col].astype(str).str.replace(',', '').str.strip()
                    df[col] = df[col].str.replace(r'\.0$', '', regex=True)  # '5.0' -> '5'
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"⚠️ Lỗi khi xử lý file {file_path}: {e}")
            raise
    raise UnicodeDecodeError(f"Không đọc được file {file_path} với UTF-8 hoặc cp1252!")

# === LOAD DỮ LIỆU BAN ĐẦU (vẫn load để có cấu trúc, nhưng routes đọc file tươi) ===
hotels = read_csv_safe(HOTELS_CSV)
reviews_df = read_csv_safe(REVIEWS_CSV)

if 'name' not in hotels.columns:
    if 'Name' in hotels.columns:
        hotels = hotels.rename(columns={'Name': 'name'})
    else:
        raise KeyError("❌ hotels.csv không có cột 'name'!")

if 'hotel_name' not in reviews_df.columns:
    raise KeyError("❌ reviews.csv không có cột 'hotel_name'.")


# === HÀM HỖ TRỢ MAPPING / ICON ===
def yes_no_icon(val):
    return "✅" if str(val).lower() in ("true", "1", "yes") else "❌"

def map_hotel_row(row):
    h = dict(row)
    h["image"] = h.get("image_url", h.get("image", ""))
    html_desc = h.get("review") or h.get("description") or ""
    h["full_desc"] = html_desc
    clean = re.sub(r'<[^>]*>', '', html_desc)
    h["short_desc"] = clean[:150] + ("..." if len(clean) > 150 else "")
    h["gym"] = h.get("gym", False)
    h["spa"] = h.get("spa", False)
    h["sea_view"] = h.get("sea") if "sea" in h else h.get("sea_view", False)
    return h


# === TRANG CHỦ ===
@app.route('/')
def home():
    hotels_df = read_csv_safe(HOTELS_CSV)
    # đảm bảo cột rooms_available và status tồn tại và đúng kiểu
    if 'rooms_available' not in hotels_df.columns:
        hotels_df['rooms_available'] = 0
    hotels_df['rooms_available'] = hotels_df['rooms_available'].astype(int)
    if 'status' not in hotels_df.columns:
        hotels_df['status'] = hotels_df['rooms_available'].apply(lambda x: 'còn' if int(x) > 0 else 'hết')

    cities = sorted(hotels_df['city'].dropna().unique())
    return render_template('index.html', cities=cities)


# === TRANG GỢI Ý ===
@app.route('/recommend', methods=['POST', 'GET'])
def recommend():
    filtered = read_csv_safe(HOTELS_CSV)

    # đảm bảo cột status và rooms_available tồn tại và đúng kiểu
    if 'rooms_available' not in filtered.columns:
        filtered['rooms_available'] = 0
    # rooms_available đã numeric từ read_csv_safe -> chỉ ép kiểu int cho chắc
    filtered['rooms_available'] = filtered['rooms_available'].astype(int)
    if 'status' not in filtered.columns:
        filtered['status'] = filtered['rooms_available'].apply(lambda x: 'còn' if int(x) > 0 else 'hết')
    else:
        # nếu status tồn tại nhưng có giá trị lạ, chuẩn hóa theo rooms_available
        filtered['status'] = filtered['rooms_available'].apply(lambda x: 'còn' if int(x) > 0 else 'hết')

    if request.method == 'POST':
        city = request.form.get('location', '').lower()
        budget = request.form.get('budget', '')
        stars = request.form.get('stars', '')
    else:
        city = request.args.get('location', '').lower()
        budget = request.args.get('budget', '')
        stars = request.args.get('stars', '')

    if city:
        filtered = filtered[filtered['city'].str.lower() == city]

    if budget:
        try:
            budget = float(budget)
            filtered = filtered[filtered['price'] <= budget]
        except Exception:
            pass

    if stars:
        try:
            stars = int(stars)
            filtered = filtered[filtered['stars'] >= stars]
        except Exception:
            pass

    results = [map_hotel_row(r) for r in filtered.to_dict(orient='records')]
    return render_template('result.html', hotels=results)


# === TRANG CHI TIẾT ===
@app.route('/hotel/<name>')
def hotel_detail(name):
    hotels_df = read_csv_safe(HOTELS_CSV)

    if 'rooms_available' not in hotels_df.columns:
        hotels_df['rooms_available'] = 0
    hotels_df['rooms_available'] = hotels_df['rooms_available'].astype(int)
    if 'status' not in hotels_df.columns:
        hotels_df['status'] = hotels_df['rooms_available'].apply(lambda x: 'còn' if int(x) > 0 else 'hết')
    else:
        hotels_df['status'] = hotels_df['rooms_available'].apply(lambda x: 'còn' if int(x) > 0 else 'hết')

    hotel_data = hotels_df[hotels_df['name'] == name]

    if hotel_data.empty:
        return "<h3>Không tìm thấy khách sạn!</h3>", 404

    hotel = map_hotel_row(hotel_data.iloc[0].to_dict())
    reviews_df_local = read_csv_safe(REVIEWS_CSV)
    hotel_reviews = reviews_df_local[reviews_df_local['hotel_name'] == name].to_dict(orient='records')

    avg_rating = (
        round(sum(float(r.get('rating', 0)) for r in hotel_reviews) / len(hotel_reviews), 1)
        if hotel_reviews else hotel.get('rating', 'Chưa có')
    )

    features = {
        "Buffet": yes_no_icon(hotel.get("buffet")),
        "Bể bơi": yes_no_icon(hotel.get("pool")),
        "Gần biển": yes_no_icon(hotel.get("sea_view") or hotel.get("sea")),
        "View biển": yes_no_icon(hotel.get("view")),
    }

    rooms = [
        {"type": "Phòng nhỏ", "price": round(float(hotel.get('price', 0)) * 1.0)},
        {"type": "Phòng đôi", "price": round(float(hotel.get('price', 0)) * 1.5)},
        {"type": "Phòng tổng thống", "price": round(float(hotel.get('price', 0)) * 2.5)},
    ]

    return render_template('detail.html', hotel=hotel, features=features, rooms=rooms,
                           reviews=hotel_reviews, avg_rating=avg_rating)


# === GỬI ĐÁNH GIÁ ===
@app.route('/review/<name>', methods=['POST'])
def add_review(name):
    user = request.form.get('user', 'Ẩn danh').strip()
    rating = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()

    new_review = pd.DataFrame([{
        "hotel_name": name,
        "user": user,
        "rating": rating,
        "comment": comment
    }])

    df = read_csv_safe(REVIEWS_CSV)
    df = pd.concat([df, new_review], ignore_index=True)
    df.to_csv(REVIEWS_CSV, index=False, encoding="utf-8-sig")

    return redirect(url_for('hotel_detail', name=name))

# === TRANG ĐẶT PHÒNG ===
@app.route('/booking/<name>/<room_type>', methods=['GET', 'POST'])
def booking(name, room_type):
    hotels_df = read_csv_safe(HOTELS_CSV)
    if 'rooms_available' not in hotels_df.columns:
        hotels_df['rooms_available'] = 0
    hotels_df['rooms_available'] = hotels_df['rooms_available'].astype(int)
    if 'status' not in hotels_df.columns:
        hotels_df['status'] = hotels_df['rooms_available'].apply(lambda x: 'còn' if int(x) > 0 else 'hết')
    else:
        hotels_df['status'] = hotels_df['rooms_available'].apply(lambda x: 'còn' if int(x) > 0 else 'hết')

    hotel_data = hotels_df[hotels_df['name'] == name]

    if hotel_data.empty:
        return "<h3>Không tìm thấy khách sạn!</h3>", 404

    hotel = map_hotel_row(hotel_data.iloc[0].to_dict())

    # --- 🟢 LẤY STATUS MỚI NHẤT TỪ CSV ---
    hotel_row = hotels_df[hotels_df['name'] == name].iloc[0]
    hotel['status'] = 'còn' if int(hotel_row['rooms_available']) > 0 else 'hết'
    is_available = hotel['status'].lower() == 'còn'
    flash(f"Trạng thái phòng hiện tại: {hotel['status']}", "info")

    # --- 🛑 Kiểm tra trạng thái phòng ---
    if not is_available:
        flash("Khách sạn này hiện đã hết phòng. Vui lòng chọn khách sạn khác.", "danger")
        #return redirect(url_for('home'))  # chuyển về trang chủ

    # Xử lý POST đặt phòng
    if request.method == 'POST':
        info = {
            "hotel_name": name,
            "room_type": room_type,
            "price": float(request.form.get('price', hotel.get('price', 0))),
            "user_name": request.form['fullname'].strip(),
            "phone": request.form['phone'].strip(),
            "email": request.form.get('email', '').strip(),
            "num_adults": max(int(request.form.get('adults', 1)), 1),
            "num_children": max(int(request.form.get('children', 0)), 0),
            "checkin_date": request.form['checkin'],
            "nights": 1,
            "special_requests": request.form.get('note', '').strip(),
            "booking_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Chờ xác nhận"
        }

        # Ghi CSV đặt phòng
        try:
            df = pd.read_csv(BOOKINGS_CSV, encoding="utf-8-sig")
        except FileNotFoundError:
            df = pd.DataFrame(columns=info.keys())
        df = pd.concat([df, pd.DataFrame([info])], ignore_index=True)
        df.to_csv(BOOKINGS_CSV, index=False, encoding="utf-8-sig")

        # Gửi email khách
        if info["email"]:
            try:
                msg_user = Message(
                    subject="Xác nhận đặt phòng - Hotel Pinder",
                    recipients=[info["email"]]
                )
                msg_user.html = f"""..."""  # giữ nguyên nội dung email
                mail.send(msg_user)
            except Exception as e:
                print(f"⚠️ Lỗi gửi email cho khách: {e}")

        # Gửi email admin
        try:
            msg_admin = Message(
                subject=f"🔔 Đơn đặt phòng mới tại {info['hotel_name']}",
                recipients=["hotelpinder@gmail.com"]
            )
            msg_admin.html = f"""..."""  # giữ nguyên nội dung email admin
            mail.send(msg_admin)
        except Exception as e:
            print(f"⚠️ Lỗi gửi email admin: {e}")

        return render_template('success.html', info=info)

    return render_template('booking.html', hotel=hotel, room_type=room_type, is_available=is_available)



# === LỊCH SỬ ĐẶT PHÒNG ===
@app.route('/history', methods=['GET', 'POST'])
def booking_history():
    bookings = []
    email = ""

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if os.path.exists(BOOKINGS_CSV) and email:
            df = pd.read_csv(BOOKINGS_CSV, encoding='utf-8-sig')
            df['email'] = df['email'].astype(str).str.lower()
            bookings = df[df['email'] == email].to_dict(orient='records')

    return render_template('history.html', bookings=bookings, email=email)


# === TRANG GIỚI THIỆU ===
@app.route('/about')
def about_page():
    return render_template('about.html')

# === ĐĂNG NHẬP QUẢN TRỊ ===
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        # ⚙️ Tài khoản admin cố định (có thể sửa)
        if username == "admin" and password == "123456":
            session['admin'] = True
            flash("Đăng nhập thành công!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Sai tài khoản hoặc mật khẩu!", "danger")
    return render_template('admin_login.html')


# === ĐĂNG XUẤT ===
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    flash("Đã đăng xuất!", "info")
    return redirect(url_for('admin_login'))


# === TRANG DASHBOARD QUẢN TRỊ ===
@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    # Đọc dữ liệu
    hotels_df = pd.read_csv(HOTELS_CSV, encoding='utf-8-sig')
    bookings_df = pd.read_csv(BOOKINGS_CSV, encoding='utf-8-sig') if os.path.exists(BOOKINGS_CSV) else pd.DataFrame()

    total_hotels = len(hotels_df)
    total_bookings = len(bookings_df)
    total_cities = hotels_df['city'].nunique()

    return render_template('admin_dashboard.html',
                           total_hotels=total_hotels,
                           total_bookings=total_bookings,
                           total_cities=total_cities)


@app.route('/admin/hotels', methods=['GET', 'POST'])
def admin_hotels():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    # Đọc file khách sạn
    df = pd.read_csv(HOTELS_CSV, encoding='utf-8-sig')

    # --- Đảm bảo các cột cần thiết có tồn tại ---
    if 'rooms_available' not in df.columns:
        df['rooms_available'] = 1
    if 'status' not in df.columns:
        df['status'] = 'còn'

    # --- Xử lý dữ liệu bị thiếu hoặc NaN ---
    # Chuyển kiểu an toàn (loại '5.0' -> '5', loại dấu phẩy)
    df['rooms_available'] = df['rooms_available'].astype(str).str.replace(',', '').str.strip()
    df['rooms_available'] = df['rooms_available'].str.replace(r'\.0$', '', regex=True)
    df['rooms_available'] = pd.to_numeric(df['rooms_available'], errors='coerce').fillna(0).astype(int)
    df['status'] = df['rooms_available'].apply(lambda x: 'còn' if x > 0 else 'hết')
    df.to_csv(HOTELS_CSV, index=False, encoding='utf-8-sig')


    # --- Thêm khách sạn mới ---
    if request.method == 'POST' and 'name' in request.form and 'add_hotel' not in request.form:
        name = request.form.get('name', '').strip()
        city = request.form.get('city', '').strip()
        price = request.form.get('price', '').strip()
        stars = request.form.get('stars', '').strip()
        description = request.form.get('description', '').strip()
        rooms_available = request.form.get('rooms_available', 1)

        try:
            rooms_available = int(float(str(rooms_available).replace(',', '').replace('.0', '')))
        except Exception:
            rooms_available = 1

        if name and city:
            new_row = {
                "name": name,
                "city": city,
                "price": price,
                "stars": stars,
                "description": description,
                "rooms_available": rooms_available,
                "status": "còn" if rooms_available > 0 else "hết"
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_csv(HOTELS_CSV, index=False, encoding='utf-8-sig')
            flash("✅ Đã thêm khách sạn mới!", "success")
            return redirect(url_for('admin_hotels'))
        else:
            flash("⚠️ Tên và thành phố không được để trống!", "warning")

    # --- Cập nhật số phòng còn ---
    if request.method == 'POST' and 'update_hotel' in request.form:
        update_name = request.form.get('update_name', '').strip()
        update_rooms = request.form.get('update_rooms', '').strip()

        try:
            update_rooms = int(float(str(update_rooms).replace(',', '').replace('.0', '')))
        except ValueError:
            update_rooms = 0

        if update_name in df['name'].values:
            df.loc[df['name'] == update_name, 'rooms_available'] = update_rooms
            df.loc[df['name'] == update_name, 'status'] = 'còn' if update_rooms > 0 else 'hết'
            df.to_csv(HOTELS_CSV, index=False, encoding='utf-8-sig')
            flash(f"🔧 Đã cập nhật số phòng cho {update_name}", "success")
        else:
            flash("⚠️ Không tìm thấy khách sạn có tên này!", "danger")

    hotels = df.to_dict(orient='records')
    return render_template('admin_hotels.html', hotels=hotels)


# === Quản lý đặt phòng (Admin) ===
@app.route('/admin/bookings')
def admin_bookings():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    if os.path.exists(BOOKINGS_CSV):
        df = pd.read_csv(BOOKINGS_CSV, encoding='utf-8-sig')
        bookings = df.to_dict(orient='records')
    else:
        bookings = []

    return render_template('admin_bookings.html', bookings=bookings)


# === Xác nhận đặt phòng ===
@app.route('/admin/bookings/confirm/<booking_time>')
def admin_confirm_booking(booking_time):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    df = pd.read_csv(BOOKINGS_CSV, encoding='utf-8-sig')
    df.loc[df['booking_time'] == booking_time, 'status'] = 'Đã xác nhận'
    df.to_csv(BOOKINGS_CSV, index=False, encoding='utf-8-sig')
    flash("Đã xác nhận đặt phòng!", "success")
    return redirect(url_for('admin_bookings'))


# === Xóa đặt phòng ===
@app.route('/admin/bookings/delete/<booking_time>')
def admin_delete_booking(booking_time):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    df = pd.read_csv(BOOKINGS_CSV, encoding='utf-8-sig')
    df = df[df['booking_time'] != booking_time]
    df.to_csv(BOOKINGS_CSV, index=False, encoding='utf-8-sig')
    flash("Đã xóa đặt phòng!", "info")
    return redirect(url_for('admin_bookings'))


# === XÓA KHÁCH SẠN ===
@app.route('/admin/hotels/delete/<name>')
def delete_hotel(name):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    try:
        df = pd.read_csv(HOTELS_CSV, encoding='utf-8-sig')
        df = df[df['name'] != name]
        df.to_csv(HOTELS_CSV, index=False, encoding='utf-8-sig')
        flash(f"Đã xóa khách sạn: {name}", "info")
    except Exception as e:
        flash(f"Lỗi khi xóa khách sạn: {e}", "danger")
    return redirect(url_for('admin_hotels'))


# === CẬP NHẬT TRẠNG THÁI KHÁCH SẠN ===
@app.route('/admin/hotels/status/<name>/<status>')
def update_hotel_status(name, status):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    try:
        # --- Đọc CSV trước ---
        df = pd.read_csv(HOTELS_CSV, encoding='utf-8-sig')

        if name in df['name'].values:
            # ✅ Cập nhật trạng thái
            df.loc[df['name'] == name, 'status'] = status

            # ✅ Đồng bộ rooms_available
            if status.strip().lower() == 'còn':
                # Nếu admin set "còn" mà rooms_available = 0 thì tự đặt = 1
                df.loc[df['name'] == name, 'rooms_available'] = df.loc[df['name'] == name, 'rooms_available'].replace(0, 1)
            elif status.strip().lower() == 'hết':
                df.loc[df['name'] == name, 'rooms_available'] = 0

            # Đồng bộ lại status theo rooms_available để hiển thị đúng trên booking
            df['status'] = df['rooms_available'].apply(lambda x: 'còn' if x > 0 else 'hết')

            df.to_csv(HOTELS_CSV, index=False, encoding='utf-8-sig')
            flash(f"✅ Đã cập nhật {name} → {status}", "success")
        else:
            flash("⚠️ Không tìm thấy khách sạn này!", "warning")
    except Exception as e:
        flash(f"Lỗi khi cập nhật trạng thái: {e}", "danger")
    return redirect(url_for('admin_hotels'))


# === KHỞI CHẠY APP ===
if __name__ == '__main__':
    app.run(debug=True)


