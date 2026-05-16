import unittest

from bs4 import BeautifulSoup

from services.crawler_service_legacy import extract_musinsa_thumbnail_urls


class MusinsaImageExtractionTests(unittest.TestCase):
    def test_extracts_srcset_and_state_images(self):
        soup = BeautifulSoup(
            """
            <html><head>
              <meta property="og:image" content="//image.msscdn.net/images/goods_img/202605/6044710/main.jpg">
            </head><body>
              <img srcset="//image.msscdn.net/images/goods_img/202605/6044710/side_500.jpg 1x,
                           //image.msscdn.net/images/goods_img/202605/6044710/side_big.jpg 2x">
              <img data-srcset="//image.msscdn.net/images/prd_img/202605/6044710/detail_500.jpg 1x">
            </body></html>
            """,
            "html.parser",
        )
        product_json = {"image": "//image.msscdn.net/images/goods_img/202605/6044710/front.jpg"}
        mss_state = {
            "goodsNo": "6044710",
            "thumbnailImages": [
                {"imageUrl": "//image.msscdn.net/images/goods_img/202605/6044710/back.jpg?width=500"},
            ],
        }

        urls = extract_musinsa_thumbnail_urls(
            soup=soup,
            product_json=product_json,
            goods_no="6044710",
            max_thumbnail_images=None,
            mss_state=mss_state,
        )

        self.assertGreaterEqual(len(urls), 5)
        self.assertTrue(any(url.endswith("/front.jpg") for url in urls))
        self.assertTrue(any(url.endswith("/back.jpg") for url in urls))
        self.assertTrue(any(url.endswith("/side_500.jpg") for url in urls))
        self.assertTrue(any(url.endswith("/detail_500.jpg") for url in urls))

    def test_extracts_detail_images_from_goods_contents_html(self):
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        mss_state = {
            "goodsNo": "6044710",
            "thumbnailImageUrl": "/images/goods_img/20260223/6044710/6044710_17718422966100_500.png",
            "goodsContents": """
                <div><img src="//image.msscdn.net/images/prd_img/2026022318442816019715393699c217c271cf.jpg"></div>
                <div><img data-src="//image.msscdn.net/images/prd_img/2026022318442843379095950699c217c69e89.jpg"></div>
            """,
        }

        urls = extract_musinsa_thumbnail_urls(
            soup=soup,
            product_json={},
            goods_no="6044710",
            max_thumbnail_images=None,
            mss_state=mss_state,
        )

        self.assertEqual(
            urls,
            [
                "https://image.msscdn.net/images/goods_img/20260223/6044710/6044710_17718422966100_500.png",
                "https://image.msscdn.net/images/prd_img/2026022318442816019715393699c217c271cf.jpg",
                "https://image.msscdn.net/images/prd_img/2026022318442843379095950699c217c69e89.jpg",
            ],
        )


if __name__ == "__main__":
    unittest.main()
