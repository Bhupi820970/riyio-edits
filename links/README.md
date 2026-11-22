# links/ — apne YouTube links yahan daalo

**Kaise add kare (bas itna):**
1. GitHub pe `links/queue.txt` kholo → ✏️ (Edit) dabao.
2. Har line me **ek** YouTube link paste karo (jaise `https://www.youtube.com/watch?v=...`).
   `#` se shuru hone wali line comment hoti hai, wo ignore hoti hai.
3. "Commit changes" dabao. Bas ho gaya.

**Phir kya hota hai:**
- Har run me pipeline **sabse pehle** `queue.txt` ka agla naya (unused) link uthata hai.
- Wahi RapidAPI downloader → Gemini check (logo / subtitles / fan edit nahi hona chahiye) → captions, music, QC.
- Link use hone ke baad `links/used.txt` me likh diya jata hai (`used` ya `rejected` + reason), aur bot (bibi-bot) usko main pe commit kar deta hai. Isliye same link dobara nahi chalega.
- Agar clip reject hua (logo, subtitles, English nahi, etc.), to `rejected` + reason likh ke agla link try hota hai.
- Jab queue me koi naya link nahi bacha, tab `channels/channels.txt` ke channels se clips aate hain, aur unke baad pipeline khud search karta hai (auto search).

**Ek hi link turant chalana ho:** Actions → riyio-v2 → Run workflow → `source_url` me link daalo. Ye queue se upar chalta hai (override).

Tips: official channel ka clean upload do (koi logo / watermark / burned subtitles nahi), English dialogue, 1080p ya usse upar.
