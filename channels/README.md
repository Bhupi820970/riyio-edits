# channels/ — clean (bina watermark) YouTube channels yahan daalo

**Channel kaise add kare:**
1. GitHub pe `channels/channels.txt` kholo → ✏️ (Edit).
2. Har line me **ek** channel link daalo, jaise `https://www.youtube.com/@joblomovieclips`.
   `#` se shuru hone wali line comment hai.
3. "Commit changes" dabao.

**Pipeline ka order (har run):**
1. `source_url` (Run workflow me diya ho to) →
2. `links/queue.txt` ke naye links →
3. **yahan ke channels** ke recent/popular videos (scene / clip wale, 2-12 min, compilation/trailer/interview skip) →
4. auto search.

**Dhyan rahe:**
- Channel pe bharosa andha nahi hai: har video ka Gemini logo / subtitles / fan-edit pre-check hota hai.
- Jo video use ya reject hua, uska ID `links/used.txt` me jata hai (dobara nahi aayega).
- Agar kisi channel ke videos logo ki wajah se reject hote hain, to channel `config/rejected_channels.json` me chala jata hai aur skip hota hai.
