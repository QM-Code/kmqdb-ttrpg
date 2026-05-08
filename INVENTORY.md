# Image Inventory

Generated from `data/inventory/paizo_digital_image_inventory.csv`. The project currently stores image URLs, not downloaded image binaries. Disk-space values below are calculated from CDN `Content-Length` headers and represent the estimated local storage required if the thumbnail and full-size image sets were downloaded.

| Game | Products | Image Records | Thumbnail Files | Thumbnail Size | Full-Size Files | Full-Size Size | Combined Size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pathfinder 1E | 58 | 58 | 58 | 2.8 MB | 58 | 9.2 MB | 12.0 MB |
| Pathfinder 2E | 28 | 111 | 111 | 3.5 MB | 111 | 130.5 MB | 134.0 MB |
| Pathfinder 2E Remaster | 59 | 187 | 187 | 7.7 MB | 187 | 215.5 MB | 223.2 MB |
| Starfinder 1E | 2 | 2 | 2 | 77.7 KB | 2 | 547.5 KB | 625.2 KB |
| Starfinder 2E | 10 | 29 | 29 | 860.6 KB | 29 | 25.6 MB | 26.5 MB |

## Totals

- Products: `157`
- Image records: `387`
- Thumbnail files: `387` (14.9 MB)
- Full-size files: `387` (381.4 MB)
- Combined estimated image storage: `396.3 MB`

## Notes

- `Image Records` means one product image row in the CSV. A product can have more than one image.
- `Thumbnail Files` are the `thumbnail_url` entries in the CSV.
- `Full-Size Files` are the `full_size_url` entries in the CSV.
- Sizes may change if Paizo updates or recompresses CDN assets.
