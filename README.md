# SRT Whiteboard Animation Skill (bản tiếng Việt)

> Đây là bản dịch tiếng Việt của [geeklee/srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation) (MIT License). Toàn bộ mã nguồn và ý tưởng thuộc về tác giả gốc. Bản này chỉ dịch tài liệu, chú thích, thông báo trên dòng lệnh và giao diện trang xem trước sang tiếng Việt.

Skill biến phụ đề SRT thành video whiteboard vẽ tay theo đúng thứ tự câu chuyện. Skill kết hợp **dàn dựng theo vùng bằng mặt nạ** với **nét bút chảy liên tục**: mỗi phần tử xuất hiện theo phụ đề, đầu bút hạ mực liên tục trong vùng của nó rồi tô màu dần, cuối cùng xuất ra MP4.

Phù hợp để làm video giảng giải kiến thức, kể chuyện, bài giảng hoặc văn bản video ngắn thành hoạt ảnh vẽ tay trên nền giấy màu be ấm.

## Ví dụ

**Cảnh: khỉ giành chuối trên núi đá.** Theo thứ tự phụ đề, lần lượt vẽ núi đá và khỉ con, khỉ lớn giật chuối, rồi các em nhỏ đứng xem.

![Khỉ giành chuối trên núi đá: demo SRT Whiteboard Animation](examples/scene-01-monkey-mountain-stream.gif)

Ảnh phác thảo gốc: [xem PNG](examples/scene-01-monkey-mountain.png).

## Tính năng chính

- Đọc phụ đề SRT, chia cảnh theo thời lượng gợi ý 25–35 giây
- Đưa ra phân cảnh và chiến lược hình ảnh trước, mỗi cảnh chỉ diễn đạt một ý chính
- Sắp xếp thứ tự vẽ theo sự kiện trong phụ đề chứ không theo tọa độ trên hình
- Quản lý vùng, thời gian, liên kết phụ đề và vùng bảo vệ chồng lấn bằng `annotation.json`
- Mỗi vùng dùng nét stream liên tục: `ink` phác nét trước, `color` tô màu sau
- Có trang xem trước trên trình duyệt để chỉnh vùng, thứ tự, thời gian và liên kết phụ đề
- Render từng cảnh rồi ghép nhiều cảnh, xuất ra MP4 hoàn chỉnh

## Cách làm việc

Điểm mấu chốt của skill là "phụ đề dẫn dắt, xác nhận từng bước". Sau mỗi bước đều phải chờ xác nhận, tránh lãng phí chi phí render khi phân cảnh, ảnh phác thảo hay annotation chưa chốt:

1. Đọc SRT, xuất phân cảnh và chiến lược hình ảnh.
2. Sau khi xác nhận, tạo ảnh phác thảo cùng phong cách.
3. Sau khi xác nhận ảnh phác thảo, kết hợp phụ đề và ảnh gốc để tạo annotation, rồi nạp vào trang xem trước.
4. Sau khi xác nhận annotation, tạo ảnh kiểm tra phân vùng và hướng vẽ.
5. Trong trang xem trước, chỉnh vùng, thứ tự kể chuyện, thời gian và liên kết phụ đề rồi lưu.
6. Sau khi xác nhận annotation cuối cùng, render MP4 từng cảnh.
7. Với dự án nhiều cảnh, sau khi xác nhận từng cảnh thì ghép lại.

## Quy chuẩn hình ảnh

- Nền giấy be ấm, gợi ý `#F5EBD7`
- Nét chì xám đậm, chỉ điểm xuyết ít màu đỏ, cam, xanh dương
- Vẽ tay tối giản, nền sạch, nhiều khoảng trắng
- Không dùng chữ trong cảnh, nhãn, cảm giác ảnh chụp, hiệu ứng 3D hay họa tiết phức tạp

## Cài đặt và môi trường

Skill có sẵn script chuẩn bị môi trường ảo Python riêng. Lần chạy đầu tiên:

```
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

Khi thành công, lệnh đầu tiên in ra `ENV_PY=<đường dẫn>`. Các lần render sau hãy dùng đúng trình thông dịch này để cô lập thư viện.

## Cấu trúc thư mục dự án

```
assets/whiteboard/<tên dự án>/
├── scene-01-<tên>.png
├── scene-01-<tên>.annotation.json
├── scene-01-<tên>-whiteboard.mp4
└── scene-01-<tên>-preview.mp4
```

Ảnh và annotation phải trùng tên, ví dụ `scene-01-demo.png` ứng với `scene-01-demo.annotation.json`.

## Định dạng annotation

Mỗi phần tử dùng tọa độ pixel nguyên của ảnh gốc, và liên kết với sự kiện trong phụ đề qua `sequence`, `subtitle` và `narrativeRole`. Các vùng nên sắp theo thứ tự "bối cảnh → nhân vật/vật chính → hành động hoặc biến đổi → phản ứng/kết quả".

```
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Khỉ con cầm chuối trên núi khỉ, khỉ lớn giật mất quả chuối, các em nhỏ đứng bên xem.",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Cảnh núi khỉ",
      "sequence": 1,
      "narrativeRole": "Bối cảnh mở đầu của câu chuyện",
      "subtitle": "Chú khỉ con ngồi trên đỉnh núi khỉ, tay cầm quả chuối.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": {
        "direction": "top_to_bottom",
        "startMs": 300,
        "durationMs": 2600,
        "maskPaddingPx": 22,
        "protectedRegions": []
      },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

`direction` và `handPath` chỉ dùng cho bản đại diện hình chữ nhật trong trang xem trước. Nét bút thật trong video hoàn chỉnh do bộ render stream tự tạo. Với các đối tượng che khuất nhau, hãy ghi vùng cần hiện muộn vào `protectedRegions` của phần tử vẽ trước để nội dung phía sau không lộ ra sớm.

## Các lệnh hay dùng

Đọc phụ đề và đề xuất phân cảnh:

```
python scripts/parse_srt.py <phụ_đề.srt> --target-sec 30 --min-sec 25 --max-sec 35
```

Tạo ảnh kiểm tra vùng:

```
python scripts/render_annotation_preview.py <đường_dẫn_ảnh> <đường_dẫn_annotation> <ảnh_xem_trước_xuất_ra>
```

Mở `assets/preview.html`, dùng nút "Mở thư mục" để nạp thư mục cảnh, từ đó có thể chỉnh vùng, thứ tự, thời gian và liên kết phụ đề.

Render một cảnh:

```
<ENV_PY> scripts/render_stream_whiteboard.py <đường_dẫn_ảnh> <đường_dẫn_annotation> <output.mp4> assets/drawing-hand.png \
  --ink-path grid --color-fill contour-wipe
```

Ghép nhiều cảnh:

```
<ENV_PY> scripts/merge_scenes.py --inputs canh1.mp4 canh2.mp4 canh3.mp4 --output final.mp4
```

## Kiểm tra chất lượng

- Khung hình đầu là nền giấy be ấm sạch, không lộ nét nào sớm
- `canvas` khớp kích thước ảnh gốc, mọi vùng là tọa độ pixel nguyên nằm trong canvas
- `sequence`, `startMs` khớp thứ tự kể chuyện của phụ đề
- Ở các khung giữa video, vùng chưa tới lượt và vùng bảo vệ không hiện sớm
- Đầu bút bám sát nét đang vẽ; nếu nét phác rõ có thể chọn `--ink-path skeleton`
- Mỗi cảnh dừng ít nhất 0,5 giây ở khung hoàn chỉnh khi kết thúc; thứ tự ghép nhiều cảnh khớp với phân cảnh phụ đề

## Nội dung repo

```
srt-whiteboard-animation/
├── SKILL.md                         # Quy trình đầy đủ và các ràng buộc
├── assets/
│   ├── drawing-hand.png              # Ảnh bàn tay
│   ├── preview.html                  # Trang xem trước/chỉnh sửa cục bộ
├── examples/                         # Tư liệu ví dụ của README
├── scripts/
│   ├── parse_srt.py                  # Phân tích phụ đề và đề xuất phân cảnh
│   ├── render_annotation_preview.py  # Ảnh kiểm tra annotation
│   ├── render_stream_whiteboard.py   # Bộ render MP4 nét bút chảy
│   ├── merge_scenes.py               # Ghép nhiều cảnh
│   └── prepare_env.py                # Chuẩn bị môi trường thư viện
└── agents/openai.yaml                # Metadata cho Codex
```

## Đóng góp

Hoan nghênh gửi Issue hoặc Pull Request. Mọi thay đổi liên quan đến logic vẽ nên được kiểm tra bằng phụ đề, annotation và video thật để xác nhận việc bảo vệ mặt nạ, thời gian và hình ảnh cuối cùng.

## Giấy phép

Dự án gốc được phát hành theo MIT License, xem [LICENSE](LICENSE).

## Về tác giả gốc

Tác giả: geeklee, một AI Builder, dùng đội ngũ AI để xây dựng công ty một người. Kênh: Douyin, Bilibili, WeChat Official Account "江哥是老登啊".
