import streamlit as st
import pandas as pd
import re 
from filter import filter_by_location, filter_by_budget
from recommend import calculate_scores_and_explain



def parse_budget(text):
    """Trích xuất một con số từ văn bản"""
    numbers = re.findall(r'\d+', text.replace(',', '').replace('.', ''))
    if numbers:
        return int(numbers[0])
    return None

def parse_city(text):
    """Kiểm tra các thành phố đã biết"""
    text_lower = text.lower()
    if "hanoi" in text_lower or "hà nội" in text_lower:
        return "Hanoi"
    if "da nang" in text_lower or "đà nẵng" in text_lower:
        return "Da Nang"
    if "ho chi minh" in text_lower or "sài gòn" in text_lower or "saigon" in text_lower:
        return "Ho Chi Minh City"
    return None

def parse_stars(text):
    """Trích xuất số sao (1-5)"""
    numbers = re.findall(r'[1-5]', text)
    if numbers:
        return int(numbers[0])
    return None

def parse_bool(text):
    """Kiểm tra người dùng nói 'yes'/'có'"""
    return "yes" in text.lower() or "có" in text.lower() or "ừ" in text.lower()

# --- Tải Dữ liệu ---
@st.cache_data
def load_data(csv_path):
    try:
        df = pd.read_csv(csv_path)
        return df
    except FileNotFoundError:
        st.error(f"LỖI: Không tìm thấy file {csv_path}.")
        return None

base_data = load_data("hotels.csv")

# --- Giao diện Chatbot ---
st.title("Chatbot Gợi ý Khách sạn")
st.write("Hãy chat với tôi để tìm khách sạn ưng ý nhé!")

# Khởi tạo bộ nhớ chat (session state)
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Chào bạn! Bạn muốn tìm khách sạn ở thành phố nào (Hanoi, Da Nang, Ho Chi Minh City)?"}]
# Biến để theo dõi trạng thái hội thoại
if "stage" not in st.session_state:
    st.session_state.stage = "awaiting_city"
# Biến để lưu trữ sở thích người dùng
if "user_prefs" not in st.session_state:
    st.session_state.user_prefs = {}

# Hiển thị lịch sử chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Vòng lặp xử lý Input 
if prompt := st.chat_input("Nhập câu trả lời của bạn..."):
    # Hiển thị tin nhắn của người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Logic Chatbot
    current_stage = st.session_state.stage
    
    # 1. Chờ Thành phố (City)
    if current_stage == "awaiting_city":
        city = parse_city(prompt)
        if city:
            st.session_state.user_prefs["location"] = city
            st.session_state.stage = "awaiting_budget"
            response = f"Tuyệt vời! Ngân sách tối đa của bạn cho 1 đêm là bao nhiêu (ví dụ: 1000000)?"
        else:
            response = "Tôi chưa nhận diện được thành phố. Bạn vui lòng chọn 1 trong 3: Hanoi, Da Nang, Ho Chi Minh City."
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

    # 2. Chờ Ngân sách (Budget)
    elif current_stage == "awaiting_budget":
        budget = parse_budget(prompt)
        if budget and budget > 0:
            st.session_state.user_prefs["budget"] = budget
            st.session_state.stage = "awaiting_stars"
            response = f"OK, ngân sách {budget:,} VND. Bạn muốn khách sạn tối thiểu mấy sao (1-5)?"
        else:
            response = "Vui lòng nhập một con số hợp lệ cho ngân sách (ví dụ: 1500000)."
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

    # 3. Chờ Số sao (Stars)
    elif current_stage == "awaiting_stars":
        stars = parse_stars(prompt)
        if stars:
            st.session_state.user_prefs["min_stars"] = stars
            st.session_state.stage = "awaiting_pool"
            response = f"Đã ghi nhận {stars} sao. Bạn có cần hồ bơi (pool) không (yes/no)?"
        else:
            response = "Vui lòng nhập số sao từ 1 đến 5."
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

    # 4. Chờ Hồ bơi (Pool)
    elif current_stage == "awaiting_pool":
        st.session_state.user_prefs["pool"] = parse_bool(prompt)
        st.session_state.stage = "awaiting_buffet"
        response = "Bạn có cần buffet sáng không (yes/no)?"
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

    # 5. Chờ Buffet
    elif current_stage == "awaiting_buffet":
        st.session_state.user_prefs["buffet"] = parse_bool(prompt)
        st.session_state.stage = "awaiting_text"
        response = "Cuối cùng, bạn có mô tả gì thêm không (ví dụ: 'thích yên tĩnh, gần biển')? Nếu không, cứ nói 'không' nhé."
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

    # 6. Chờ Mô tả thêm 
    elif current_stage == "awaiting_text":
        st.session_state.user_prefs["text"] = prompt if prompt.lower() not in ["không", "ko", "0"] else ""
        st.session_state.stage = "processing" # Chuyển sang trạng thái xử lý
        
        response = "OK! Tôi đã nhận đủ thông tin. Đang tìm khách sạn cho bạn... Vui lòng chờ giây lát."
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

        # GỌI HỆ THỐNG GỢI Ý 
        if base_data is not None:
            with st.spinner("Đang phân tích và xếp hạng..."):
                prefs = st.session_state.user_prefs
                
                # 1. Lọc 
                filtered_data = filter_by_location(base_data, prefs.get("location"))
                filtered_data = filter_by_budget(filtered_data, prefs.get("budget"))

                # 2. Xếp hạng AI 
                final_results_sorted, explanation = calculate_scores_and_explain(
                    filtered_data.copy(), 
                    prefs
                )

                # 3. Trả kết quả ra Chat
                st.session_state.messages.append({"role": "assistant", "content": f"💡 **Giải thích của AI:** {explanation}"})
                with st.chat_message("assistant"):
                    st.info(f"**Giải thích của AI:** {explanation}")
                
                if final_results_sorted.empty:
                    response = "Rất tiếc, không tìm thấy khách sạn nào phù hợp với tất cả tiêu chí của bạn."
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    with st.chat_message("assistant"):
                        st.warning(response)
                else:
                    response = "Đây là TOP 3 gợi ý tốt nhất cho bạn:"
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    with st.chat_message("assistant"):
                        st.success(response)
                        
                        top_3 = final_results_sorted.head(3)
                        for index, row in top_3.iterrows():
                            # Hiển thị kết quả chi tiết
                            st.markdown(f"###{row['name']} ({row['stars']} sao)")
                            st.image(row['image_url'], width=300, caption=row['name'])
                            st.markdown(f"**Giá:** `{row['price']:,} VND` | **Rating:** `{row['rating']}/5` | **Điểm AI:** `{row['recommend_score']:.2f}`")
                            st.markdown(f"**Đánh giá:** *{row['review']}*")
                            st.divider()
                
                # 4. Hoàn tất và chờ tìm lại
                response = "Bạn có muốn tìm kiếm lại không? Chỉ cần gõ 'tìm lại' nhé."
                st.session_state.messages.append({"role": "assistant", "content": response})
                with st.chat_message("assistant"):
                    st.markdown(response)
                st.session_state.stage = "done"
        else:
            st.error("Lỗi dữ liệu, không thể xử lý.")

    # 7. Trạng thái Đã xong 
    elif current_stage == "done":
        if "tìm lại" in prompt.lower() or "lại" in prompt.lower():
            # Reset
            st.session_state.messages = [{"role": "assistant", "content": "OK, bắt đầu lại nhé! Bạn muốn tìm khách sạn ở thành phố nào (Hanoi, Da Nang, Ho Chi Minh City)?"}]
            st.session_state.stage = "awaiting_city"
            st.session_state.user_prefs = {}
            st.rerun() # Tải lại trang để bắt đầu
        else:
            response = "Gõ 'tìm lại' để bắt đầu một lượt tìm kiếm mới nhé!"
            st.session_state.messages.append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)