---
name: srt-whiteboard-animation
description: Biến phụ đề SRT thành video whiteboard vẽ tay trên nền giấy màu be ấm: đọc phụ đề → đưa ra chiến lược hình ảnh → sau khi xác nhận thì tạo ảnh phác thảo cùng phong cách → đánh dấu vùng theo ngữ nghĩa câu chuyện → chỉnh trong trang xem trước → render MP4. Phần dàn dựng giữ cách "hé lộ theo vùng bằng mặt nạ" (annotation.json / sequence / startMs / protectedRegions), nhưng bên trong mỗi vùng, nét vẽ được thay bằng nét bút chảy liên tục kiểu stream (khung xương/lưới, ink → color). Kích hoạt khi người dùng đưa phụ đề SRT và yêu cầu như "làm video whiteboard vẽ tay từ phụ đề", "tạo video nét bút chảy từ SRT", "tạo whiteboard animation từ SRT", "vẽ tay theo phân cảnh phụ đề", "SRT to whiteboard animation".
---

# SRT Whiteboard Animation (dàn dựng bằng mặt nạ + nét vẽ kiểu stream)

Chuyển phụ đề SRT thành video whiteboard vẽ tay. **Dàn dựng** giữ cách hé lộ theo vùng bằng mặt nạ (hé lộ từng vùng theo thứ tự câu chuyện, vùng chưa tới lượt thì ẩn hoàn toàn, phần chồng lấn được bảo vệ bằng `protectedRegions`). **Cách vẽ** thay bằng nét bút chảy liên tục: trong mặt nạ cho phép của mỗi vùng, đầu bút lướt liên tục dọc theo khung xương/lưới để hạ mực (bắt đầu `ink` → tô màu `color`). Mọi vùng dùng chung một canvas bền vững, vùng đã vẽ xong được giữ lại trên canvas. Mọi giải thích, phân cảnh, cấu hình và chữ trên giao diện hiển thị cho người dùng đều phải dùng tiếng Việt.

Khác với kiểu nhảy từng ô hay xóa theo hình chữ nhật, nét bút của skill này **chảy liền mạch**. Khác với kiểu stream toàn ảnh, skill này vẽ lần lượt theo **các vùng của câu chuyện trong phụ đề**, nên điều khiển được thứ tự xuất hiện và thời điểm của từng phần tử.

## Tham số mặc định

| Mục | Yêu cầu mặc định |
|---|---|
| Nền giấy | Ảnh tạo ra dùng màu giấy cũ be ấm (gợi ý `#F5EBD7`). Khi render, lấy mẫu màu nền từ ảnh gốc ở vị trí thụt vào từ bốn góc để nhuộm nền, cấm dùng trắng tinh. |
| Cách vẽ | Mỗi vùng dùng nét stream liên tục: `ink` (phác nét) → `color` (khôi phục màu gốc). Tỷ trọng `ink:color = 2:1`. |
| Đường đi của nét | `--ink-path grid` (lưới, mặc định, ổn định) hoặc `skeleton` (bám khung xương, hợp với tranh nét rõ). |
| Kiểu tô màu | `--color-fill contour-wipe` (quét theo đường viền, mặc định) hoặc `brush` (quét theo quỹ đạo). |
| Vùng chưa vẽ | Mặt nạ cho phép của vùng = hình chữ nhật `region` trừ đi "các vùng phía sau + protectedRegions". Vùng chưa tới lượt hoàn toàn ẩn. |
| Nguồn thời lượng | `sceneDurationMs` của mỗi ảnh lấy từ khoảng thời gian phụ đề của cảnh đó (khuyến nghị 25–35 giây/cảnh). |
| Khung chỉnh sửa | Trang xem trước mặc định hiện tất cả khung chỉnh sửa có đánh số. Khung chỉnh sửa không thuộc nội dung hình ảnh của video. |

## Quy chuẩn hình ảnh thống nhất khi tạo ảnh (bắt buộc)

Ảnh nguồn của mọi cảnh phải theo cùng một ngôn ngữ hình ảnh. Trước khi tạo, ghi đầy đủ các yêu cầu dưới đây vào prompt tạo ảnh, tạo xong thì kiểm tra từng điều:

- **Phong cách và bố cục:** minh họa vẽ tay tối giản, thuần phong cách phác thảo bằng chì, tinh thần nguệch ngoạc tiết chế kiểu Notion. Thiên về diễn đạt khái niệm, không theo đuổi chân thực. Bố cục gọn, nền sạch, nhiều khoảng trắng, cảm xúc chung bình lặng và rõ ràng, đường nét, nhân vật, màu sắc nhất quán trong cả series.
- **Màu sắc và chất liệu:** nền giấy be `#F5EBD7`, nét phác màu xám đậm. Chỉ được dùng đỏ, cam, xanh dương để điểm xuyết khái niệm với số lượng nhỏ. Không dùng màu nhấn khác, phối màu bão hòa cao hay họa tiết phức tạp.
- **Nhân vật và đối tượng:** đối tượng được thể hiện bằng đường viền đơn giản, ít nét và khoảng trắng, nhấn mạnh quan hệ/biến đổi/khái niệm cốt lõi chứ không phải tỷ lệ, chất liệu và chi tiết thực.
- **Tuyệt đối cấm:** mọi chữ, từ, chữ cái, chữ số, phông chữ hoặc nhãn trong ảnh nguồn của cảnh; cảm giác chân thực, chi tiết như ảnh chụp, hiệu ứng 3D, chất liệu hội họa; cảnh phức tạp, nền dày đặc, trang trí rườm rà và hình ảnh bão hòa cao.
- **Ngoại lệ về bàn tay vẽ:** nếu người dùng nói rõ chữ trên thân bút là dấu hiệu nhận diện của họ và yêu cầu giữ lại, có thể giữ dấu hiệu trên thân bút của `drawing-hand.png`. Nó không thuộc chữ trong ảnh nguồn của cảnh, không cần xóa hay vẽ lại. Chưa được người dùng nói rõ thì vẫn xử lý như hình không có chữ.

## Cửa xác nhận (bắt buộc)

**Sau mỗi bước** trong quy trình mặc định đều phải dừng lại và chờ người dùng xác nhận rõ ràng mới được sang bước tiếp theo. Trước khi có xác nhận, không được tạo ảnh, annotation, bản xem trước, video hay file ghép của bước sau. Không được coi "chưa trả lời", "sự cho phép chung chung từ trước" hay "người dùng không phản đối" là xác nhận. Khi người dùng yêu cầu sửa bước trước, chỉ làm lại bước đó, xong rồi lại chờ xác nhận.

Hành động đi kèm duy nhất: **sau khi tạo xong JSON annotation, phải lập tức tự động mở trang xem trước và nạp thư mục chứa JSON đó**. Việc này thuộc phần giao của bước 3, không cần chờ xác nhận riêng cho "mở trang xem trước". Nếu File System Access API của trình duyệt đòi thao tác của người dùng, hãy dùng giao diện trình duyệt để chọn đúng thư mục đã xác định. Không được vì thế mà xin thêm xác nhận hay bắt người dùng tự mở trang xem trước.

## Quy trình làm việc

1. **Đọc phụ đề, đưa ra chiến lược (chưa tạo ảnh).** Dùng `scripts/parse_srt.py` phân tích SRT thành các dòng phụ đề và đề xuất phân cảnh theo 25–35 giây/cảnh. Dựa vào đó đưa ra chiến lược hình ảnh: mã cảnh, ý diễn đạt cốt lõi, chủ thể hình ảnh, khoảng phụ đề tương ứng và `sceneDurationMs` của từng cảnh. Mỗi cảnh chỉ diễn đạt một ý chính. **Xong thì dừng, chờ người dùng xác nhận chiến lược.**
2. **Tạo ảnh phác thảo.** Chỉ sau khi người dùng xác nhận chiến lược, theo "quy chuẩn hình ảnh thống nhất" tạo từng cảnh một ảnh phác thảo 16:9 trên nền giấy cũ be ấm, nền `#F5EBD7`, giữa các chủ thể chừa đủ khoảng trắng để tự động tách vùng. Không được tạo chữ, ảnh chụp phức tạp, đối tượng chồng nhau hay yếu tố trái quy chuẩn. **Xong thì dừng, cho người dùng xem ảnh phác thảo và chờ xác nhận.**
3. **Đọc phụ đề trước rồi xem ảnh, sau đó đánh dấu và mở trang xem trước.** Chỉ sau khi người dùng xác nhận ảnh phác thảo, trước hết đọc phụ đề tương ứng với ảnh đó, sau đó thực sự xem ảnh và lấy chiều rộng/cao theo pixel của ảnh gốc. Không được chỉ dựa vào phụ đề mà đoán hình, cũng không được chỉ sắp xếp máy móc theo vị trí trên hình. Trước hết rút ra các sự kiện kể chuyện từ phụ đề, rồi ghép các chủ thể nhìn thấy trong ảnh với các sự kiện, sắp xếp thứ tự vẽ theo ngữ nghĩa "bối cảnh → nhân vật/vật chính → hành động xung đột hoặc biến đổi → phản ứng/kết quả". Sau đó tạo `<tên ảnh>.annotation.json`. Tạo xong thì lập tức dùng trình duyệt mặc định mở `assets/preview.html`, và qua nút "Mở thư mục" của trang xem trước nạp toàn bộ cặp `<tên>.png` + `<tên>.annotation.json` trong **thư mục chứa file annotation đó**. Không được chỉ đưa đường dẫn file hay bắt người dùng tự thao tác. **Khi trang xem trước đã nạp thư mục thì dừng, chờ người dùng xác nhận annotation và nội dung xem trước.**
4. **Tạo ảnh xem trước vùng.** Chỉ sau khi người dùng xác nhận annotation và nội dung xem trước, dùng `render_annotation_preview.py` xuất ảnh kiểm tra số thứ tự/hướng, đối chiếu để phân vùng khớp thứ tự câu chuyện, mọi vùng nằm trong canvas, các chủ thể chồng nhau được bảo vệ bằng `protectedRegions`. **Xong thì dừng, chờ người dùng xác nhận ảnh xem trước.**
5. **Chỉnh trong trang xem trước và lưu.** Chỉ sau khi người dùng xác nhận ảnh xem trước, chỉnh trên trang xem trước đã mở và đã nạp đúng thư mục: mặc định (chưa phát) hiện đầy đủ ảnh và các khung vùng. Canvas là **đại diện hình chữ nhật**: kéo bốn cạnh bốn góc của vùng để sửa `region`, bên phải sửa tên/hướng/**bắt đầu (ms)/kết thúc (ms)** (thời lượng = kết thúc − bắt đầu, chỉ đọc) và **phụ đề**, kéo danh sách module để **đổi thứ tự** (tự sắp lại `sequence`), chọn module sẽ tự làm nổi bật phụ đề tương ứng. Kéo thanh thời gian hoặc bấm phát để xem hé lộ (vùng chưa tới lượt không hiện). `direction` chỉ ảnh hưởng đến bản đại diện này. Sửa xong bấm "Lưu cảnh này/Lưu tất cả" để ghi lại vào `.annotation.json` gốc (gồm `subtitle` của từng vùng, và căn `sceneDurationMs` bằng thời điểm kết thúc của vùng cuối + 0,5 giây). **Lưu xong thì dừng, chờ người dùng xác nhận annotation và thời gian cuối cùng.**
6. **Render video bằng dòng lệnh.** Chỉ sau khi người dùng xác nhận annotation và thời gian cuối cùng, dùng `render_stream_whiteboard.py` render từng cảnh ra MP4 hoàn chỉnh, kiểm tra ba thời điểm: lúc mở đầu, giữa lúc một module chồng lấn bất kỳ, và cuối video. **Xong thì dừng, chờ người dùng xác nhận video.**
7. **Ghép nhiều cảnh (chỉ khi có nhiều cảnh).** Chỉ sau khi người dùng xác nhận tất cả video từng cảnh, dùng `merge_scenes.py` ghép theo thứ tự thành một video. **Xong thì dừng, chờ người dùng xác nhận video ghép cuối cùng.**

## Quy ước thư mục

Tạo trong dự án của người dùng:

```text
assets/whiteboard/<tên dự án>/
  scene-01-<tên>.png
  scene-01-<tên>.annotation.json     # trùng tên với png
  scene-01-<tên>-whiteboard.mp4      # video hoàn chỉnh
  scene-01-<tên>-preview.mp4         # đoạn thật (trang xem trước tạo, độ phân giải thấp)
```

Ảnh và cấu hình phải trùng tên: `foo.png` ứng với `foo.annotation.json`. Trang xem trước dựa vào đó để tự nạp cấu hình.

## Sắp xếp theo ngữ nghĩa và đánh dấu mức pixel (phải thực hiện)

1. **Căn cứ đọc:** trước khi đánh dấu phải có đồng thời phụ đề và ảnh gốc đã xem. Thiếu một trong hai thì xin trước, không được tạo annotation.
2. **Căn cứ thứ tự:** `sequence`, `startMs` và `label` phải phản ánh trình tự sự kiện trong phụ đề, chứ không chỉ theo trái sang phải, trên xuống dưới hay mức độ nổi bật thị giác.
3. **Căn cứ tọa độ:** mỗi module xuất `x`, `y`, `width`, `height` là số nguyên pixel theo hệ tọa độ ảnh gốc. Gốc ở góc trên bên trái, cấm dùng phần trăm/tỷ lệ/tọa độ ước chừng hay bỏ kích thước. `canvas.width`/`canvas.height` phải bằng kích thước pixel của ảnh gốc.
4. **Trường của module:** mỗi phần tử gồm `sequence`, `narrativeRole`, `subtitle`, `region`, `reveal`, `handPath`. `narrativeRole` dùng tiếng Việt nêu vai trò kể chuyện của nó trong phụ đề. `subtitle` lưu văn bản phụ đề tương ứng với vùng đó (lấy từ SRT, phục vụ liên kết trong trang xem trước và các mục đích sau này). `sequence` đánh số liên tục từ 1.
5. **Kiểm tra:** trước khi tạo bản xem trước, kiểm tra từng vùng có nằm trong canvas không, có bao trùm chủ thể nhìn thấy tương ứng không, có khớp sự kiện trong phụ đề không. Các chủ thể chồng nhau được bảo vệ bằng `protectedRegions` rồi mới vẽ module.

## Mô hình thời gian (dành riêng cho cách vẽ stream)

- **Tổng thời lượng mỗi cảnh** `sceneDurationMs` lấy từ khoảng thời gian phụ đề của cảnh (`scenes[].sceneDurationMs` của `parse_srt.py`).
- **Các vùng vẽ nối tiếp:** cách vẽ stream chỉ có một cây bút chuyển động, nên trong cùng một cảnh các vùng nên **diễn ra lần lượt theo thời gian** (`startMs` không chồng nhau): vùng sau bắt đầu từ `startMs + durationMs` của vùng trước (cộng thêm tùy chọn 100–300ms nghỉ lấy hơi). Nếu `startMs` chồng nhau, bộ render vẫn xử lý theo thứ tự, nhưng về thị giác không còn là đồng thời.
- **ink→color trong vùng:** `durationMs` của mỗi vùng được chia theo `ink:color = 2:1` thành đoạn phác nét và đoạn tô màu. `durationMs` do **thời gian bắt đầu/kết thúc** trong trang xem trước quyết định (kết thúc − bắt đầu), có thể căn theo độ dài phụ đề tương ứng của vùng đó. Cũng có thể dùng 150 pixel/giây × quãng đường vẽ làm ước lượng ban đầu.
- **Dừng hình kết thúc:** sau khi mọi vùng vẽ xong, tự kéo dài đến `sceneDurationMs`, và đảm bảo cuối video dừng ít nhất 0,5 giây ở ảnh gốc hoàn chỉnh.
- `reveal.direction` trong cách vẽ stream **không quyết định nét vẽ thật** (nét được tạo tự động từ khung xương/lưới), chỉ phục vụ bản đại diện hình chữ nhật trong trang xem trước. Giữ nó để trang xem trước dùng được.

## Bất biến của mặt nạ (tầng dàn dựng, phải thực hiện)

- Tại thời điểm `t`, một module chỉ được hiện những pixel sau `reveal.startMs ≤ t` và không vượt quá tiến độ vẽ hiện tại. Mọi nét/phần tô/hình của module chưa bắt đầu đều không được xuất hiện.
- **Mặt nạ cho phép** của mỗi vùng = hình chữ nhật `region` trừ đi `region` của toàn bộ **các module phía sau**, rồi trừ `reveal.protectedRegions` của chính module này. Việc hạ mực kiểu stream bị giới hạn trong mặt nạ cho phép, nên các vùng phía sau sẽ không lộ nét sớm.
- `protectedRegions` dùng cùng tọa độ pixel nguyên của ảnh gốc như `region`, dùng cho trường hợp hình chữ nhật quá lớn, chủ thể đan xen hoặc nét nền có thể lộ ra.
- Bộ render đã hiện thực thứ tự "hạ mực giới hạn trong mặt nạ cho phép → các vùng phía sau và vùng bảo vệ tự nhiên không bị chạm tới". Bản đại diện hình chữ nhật trong trang xem trước dùng phép trừ `destination-out` tương đương để mô phỏng cùng cách dàn dựng.

## Ví dụ cấu hình

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Tóm tắt các sự kiện trong phụ đề của cảnh này",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Cảnh núi đá",
      "sequence": 1,
      "narrativeRole": "Bối cảnh mở đầu của câu chuyện",
      "subtitle": "Trên núi khỉ, một chú khỉ con ngồi trên đỉnh núi đá, tay cầm quả chuối.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": { "direction": "top_to_bottom", "startMs": 300, "durationMs": 2600, "maskPaddingPx": 22, "protectedRegions": [] },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

> `direction` / `handPath` chỉ dùng cho bản đại diện hình chữ nhật của trang xem trước. Nét vẽ trong video hoàn chỉnh do stream tự tạo, không cần tinh chỉnh.

## Cách dùng các script

Mọi script render chạy bằng trình thông dịch `.venv` bên trong skill (cô lập thư viện).

1. **Chuẩn bị môi trường** (lần đầu hoặc khi thiếu thư viện):
   ```bash
   python scripts/prepare_env.py --check   # dò kiểm; thành công thì dòng cuối in ENV_PY=<đường dẫn>, lưu lại để dùng
   python scripts/prepare_env.py           # thiếu thì tạo .venv và cài opencv-python/numpy/av
   ```
2. **Phân tích phụ đề + đề xuất phân cảnh**:
   ```bash
   python scripts/parse_srt.py <phụ_đề.srt> --target-sec 30 --min-sec 25 --max-sec 35
   ```
3. **Ảnh xem trước đánh số vùng**:
   ```bash
   python scripts/render_annotation_preview.py <ảnh> <annotation> <ảnh_xem_trước_xuất_ra>
   ```
4. **Trang xem trước (không cần server)**: mở thẳng `assets/preview.html` bằng Chrome / Edge, bấm "Mở thư mục" chọn thư mục → nạp toàn bộ ảnh + annotation cùng tên → kéo thả chỉnh sửa → "Lưu" để ghi lại file gốc. Ghi lại cần File System Access API (Chrome/Edge). Trình duyệt khác thì tải về rồi ghi đè thủ công. Việc render vẫn chạy bằng dòng lệnh (bước 5 bên dưới).
5. **Render video một cảnh**:
   ```bash
   <ENV_PY> scripts/render_stream_whiteboard.py <ảnh> <annotation> <output.mp4> assets/drawing-hand.png \
       [--ink-path grid|skeleton] [--color-fill contour-wipe|brush] [--total-ms <mili giây>]
   ```
   Nếu không có `--total-ms` thì dùng `sceneDurationMs` trong annotation. Dòng cuối in `OUTPUT=<đường dẫn>`.
6. **Ghép nhiều cảnh**:
   ```bash
   <ENV_PY> scripts/merge_scenes.py --inputs canh1.mp4 canh2.mp4 canh3.mp4 --output final.mp4
   ```

## Kiểm tra chất lượng

Xác nhận trước/sau khi render:

- Khung hình đầu là nền giấy cũ be ấm sạch, không lộ nét nào sớm.
- Đã đọc phụ đề tương ứng và thực sự xem ảnh gốc. `canvas` khớp kích thước pixel của ảnh gốc, mọi `region` là tọa độ pixel nguyên và nằm trong canvas.
- `sequence`, `startMs` khớp thứ tự sự kiện trong phụ đề. Số thứ tự/nhãn/vùng trong ảnh xem trước đều đến từ cùng một JSON annotation.
- Kiểm tra ở ba thời điểm: lúc mở đầu, giữa lúc một module chồng lấn bất kỳ, và sau khi mọi module xong: module chưa vẽ đều không thấy, vùng bảo vệ chồng lấn không bị lộ, khung cuối hiện đầy đủ ảnh gốc.
- Đầu bút bám sát nét đang tiến lên. Với tranh nét rõ có thể dùng `--ink-path skeleton` để nét bám sát hơn.
- Sau khi mọi module kết thúc, dừng ít nhất 0,5 giây ở ảnh gốc hoàn chỉnh.
- Sau khi ghép nhiều cảnh, thứ tự và thời lượng khớp với phân cảnh của phụ đề.

Nếu cần chỉnh hiệu quả, trước hết chỉnh annotation (vùng/thứ tự/thời gian) trong trang xem trước (`assets/preview.html`) rồi lưu, sau đó mới render bằng dòng lệnh, đừng render đi render lại một cách mù quáng.
