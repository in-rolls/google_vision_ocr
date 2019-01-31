### Workflow for the Google Cloud Storage Script

```
+-------+            +-------+          +-----------+            +--------------+
|       |            |       |          |           |            |              |
|  PNG  +------------>  TIF  +---------->           +------------>  Vision API  |
|       |   Pillow   |       |  upload  |           |   request  |              |
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
