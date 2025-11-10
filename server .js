// server.js (Dùng Google Gemini API)

const express = require('express');
const { GoogleGenAI } = require('@google/genai'); // Thư viện Google Gen AI
const cors = require('cors');
require('dotenv').config();

const app = express();
const port = 3000;
const MODEL_FAST = "gemini-2.5-flash"; // Mô hình nhanh, chi phí thấp
const MODEL_SMART = "gemini-2.5-pro";  // Mô hình mạnh, tốt cho phân tích phức tạp

// --- 1. KIỂM TRA KHÓA API VÀ KHỞI TẠO CLIENT ---
// Đảm bảo bạn đã đặt GEMINI_API_KEY trong file .env
if (!process.env.GEMINI_API_KEY) {
    console.error("Lỗi: GEMINI_API_KEY không được tìm thấy trong file .env!");
    console.error("Vui lòng tạo file .env và thêm GEMINI_API_KEY='Khóa_của_bạn'");
    process.exit(1);
}

const ai = new GoogleGenAI({
    apiKey: process.env.GEMINI_API_KEY,
});

// --- 2. CẤU HÌNH MIDDLEWARE ---
app.use(cors());
app.use(express.json());

// --- 3. CẤU HÌNH PERSONA (NHÂN CÁCH BẠN ĐỒNG HÀNH) ---
const SYSTEM_PROMPT_FRIENDLY = "Bạn là 'Travel Buddy AI' - một người bạn đồng hành du lịch thân thiện, nhiệt tình, am hiểu và sử dụng tiếng Việt. Giọng văn của bạn phải vui vẻ, gần gũi, sử dụng các từ ngữ thân mật (như 'tui', 'bạn', 'nhé', 'ôi trời ơi', 'quá trời') và luôn đưa ra lời khuyên chân thành, hữu ích. Tuyệt đối không trả lời như một robot hoặc trợ lý máy móc. Hãy luôn gọi người dùng là 'bạn'.";


// --- 4. HÀM HỖ TRỢ: TẠO CẤU TRÚC MESSAGE CHO GEMINI ---
// Hàm này đảm bảo mỗi yêu cầu đều mang theo persona thân thiện
function createGeminiContents(userPrompt) {
    // Chúng ta tạo một lịch sử hội thoại ngắn để thiết lập persona
    return [
        { "role": "user", "parts": [{ text: SYSTEM_PROMPT_FRIENDLY }] },
        { "role": "model", "parts": [{ text: "Tuyệt vời, tui sẵn sàng giúp đỡ bạn rồi! Bạn cần tui làm gì nè?" }] },
        { "role": "user", "parts": [{ text: userPrompt }] }
    ];
}


// --- 5. ENDPOINT 1: TÓM TẮT REVIEW KHÁCH SẠN (Tích hợp Persona) ---
app.post('/api/summarize-reviews', async (req, res) => {
    const { reviews } = req.body;

    const reviewText = reviews.join('\n- ');
    const userPrompt = `Tui có các đánh giá khách sạn sau. Bạn tóm tắt nhanh những điểm mạnh và điểm yếu chính (tối đa 100 từ) nha. Tập trung vào Dịch vụ, Vị trí và Tiện nghi:\n\nĐánh giá:\n${reviewText}`;

    try {
        const response = await ai.models.generateContent({
            model: MODEL_FAST,
            contents: createGeminiContents(userPrompt),
            config: {
                maxOutputTokens: 300,
            }
        });

        const summary = response.text;
        res.json({ success: true, summary: summary });
    } catch (error) {
        console.error("Lỗi khi tóm tắt review:", error);
        res.status(500).json({ success: false, message: "Ối, tui đang bận xíu, bạn thử lại nha. Lỗi: " + error.message });
    }
});


// --- 6. ENDPOINT 2: TÌM KIẾM NGÔN NGỮ TỰ NHIÊN (Phân tích JSON) ---
app.post('/api/natural-search', async (req, res) => {
    const { userQuery } = req.body;

    // Yêu cầu AI chuyển đổi thành tham số JSON
    const userPrompt = `Chuyển đổi truy vấn tìm kiếm sau thành định dạng JSON để tui có thể lọc khách sạn. Các trường JSON cần có: "stars" (int), "location" (string), "amenity" (string), "price_max" (int). Nếu không có thông tin, dùng null. TRẢ VỀ DUY NHẤT ĐỐI TƯỢNG JSON.
    Truy vấn của người dùng: '${userQuery}'`;

    try {
        const response = await ai.models.generateContent({
            model: MODEL_FAST,
            contents: createGeminiContents(userPrompt),
            config: {
                // Cấu hình phản hồi là JSON để code dễ dàng xử lý
                responseMimeType: "application/json",
                maxOutputTokens: 2048,
            }
        });

        const jsonString = response.text.trim();
        const searchParams = JSON.parse(jsonString);

        // Gửi tham số tìm kiếm đã phân tích về frontend
        res.json({ success: true, searchParams: searchParams });
    } catch (error) {
        console.error("Lỗi khi xử lý tìm kiếm tự nhiên:", error);
        res.status(500).json({ success: false, message: "Tui đang bận xíu, bạn thử lại nha. Lỗi: " + error.message });
    }
});


// --- 7. ENDPOINT 3: SO SÁNH KHÁCH SẠN THÔNG MINH (Phân tích sâu) ---
app.post('/api/compare-hotels', async (req, res) => {
    const { hotelA, hotelB } = req.body;

    const comparisonData = `
    Khách sạn 1 (${hotelA.name}) có các đánh giá sau:
    ---
    ${hotelA.reviews.join('\n- ')}
    ---
    
    Khách sạn 2 (${hotelB.name}) có các đánh giá sau:
    ---
    ${hotelB.reviews.join('\n- ')}
    ---
    `;

    const userPrompt = `
    Tui đang phân vân giữa hai khách sạn này. Bạn (Travel Buddy AI) hãy giúp tui so sánh chúng một cách chi tiết và thân thiện:
    
    1.  **Phân tích riêng:** Dựa trên các đánh giá, chỉ ra 3 điểm mạnh nổi bật và 2 điểm yếu phổ biến của TỪNG khách sạn (về Vị trí, Dịch vụ, Tiện nghi, Giá trị).
    2.  **So sánh:** Chỉ rõ khách sạn nào vượt trội hơn ở khía cạnh nào.
    3.  **Lời khuyên:** Cuối cùng, đưa ra một lời khuyên chân thành và rõ ràng cho tui về việc nên chọn cái nào dựa trên phong cách du lịch phổ biến (Ví dụ: yên tĩnh hay náo nhiệt).
    
    Dữ liệu đánh giá:
    ${comparisonData}
    `;

    try {
        const response = await ai.models.generateContent({
            model: MODEL_SMART, // Dùng bản Pro để phân tích so sánh chất lượng cao
            contents: createGeminiContents(userPrompt),
            config: {
                maxOutputTokens: 1000,
            }
        });

        const comparisonResult = response.text;
        res.json({ success: true, result: comparisonResult });
    } catch (error) {
        console.error("Lỗi khi so sánh khách sạn:", error);
        res.status(500).json({ success: false, message: "Ối, tui gặp trục trặc kỹ thuật rồi! Tui đang cố sửa, bạn thử lại sau nha. Lỗi: " + error.message });
    }
});


// --- 8. KHỞI ĐỘNG SERVER ---
app.listen(port, () => {
    console.log(`Server AI (Gemini) đang chạy tại http://localhost:${port}`);
});