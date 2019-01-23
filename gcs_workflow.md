### Workflow for the Google Cloud Storage Script

```
+-------+            +-------+          +-----------+            +--------------+
|       |            |       |          |           |            |              |
|  PNG  +------------>  PDF  +---------->           +------------>  Vision API  |
|       |  img2pdf   |       |  upload  |           |   request  |              |
+-------+            +-------+          |    GCS    |            |              |
                                        |   Bucket  |            |   DOCUMENT   |
+-------+            +-------+          |           |            |     TEXT     |
|  PNG  |            |       |          |           |            |   DETECTION  |
|  +    <------------+ JSON  <----------+           <------------+              |
|  BBOX |    draw    |       | download |           |    JSON    |              |
+-------+            +---+---+          +-----------+            +--------------+
                         |
                         |
                     +---v---+
                     |       |
                     | TEXT  |
                     |       |
                     +-------+
```
