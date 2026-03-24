# ScrapAI API Documentation

## Overview

ScrapAI now includes a REST API for programmatic access to spiders, crawls, and scraped data.

## Quick Start

### 1. Install Dependencies

```bash
uv sync --group dev
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
# Database (PostgreSQL recommended for production)
DATABASE_URL=postgresql://user:password@localhost:5432/scrapai

# Redis (for rate limiting, webhooks, and background jobs)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_PREFIX=joinremotes:scrapai:prod

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
```

### 3. Run Migrations

```bash
alembic upgrade head
```

### 4. Start the API

```bash
# Development mode with auto-reload
uv run python -m uvicorn api.main:app --reload

# Production mode
uv run python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Useful local commands:

```bash
uv run python scrapai db migrate
uv run python -m uvicorn api.main:app --reload
uv run python -m dramatiq apps.web_api.workers.worker
uv run python scrapai apikey create joinremotes --project joinremotes
```

### 5. Access API Documentation

Visit `http://localhost:8000/docs` for interactive Swagger UI documentation.

## Authentication

All API endpoints require authentication using API keys.

### Creating an API Key

```bash
# Using CLI
./scrapai apikey create my-app --project default

# Or programmatically
curl -X POST http://localhost:8000/api/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app", "project": "default"}'
```

### Using API Keys

Include the API key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer sk_your_api_key_here" \
  http://localhost:8000/api/v1/spiders
```

## API Endpoints

### Spiders

#### Analyze a Source URL
```http
POST /api/v1/spiders/analyze
Authorization: Bearer sk_your_api_key_here
Content-Type: application/json

{
  "url": "https://job-boards.greenhouse.io/stackblitz",
  "project": "default",
  "use_browser": false
}
```

#### List Spiders
```http
GET /api/v1/spiders
Authorization: Bearer sk_your_api_key_here
```

#### Create or Upsert Spider
```http
POST /api/v1/spiders?project=default
Authorization: Bearer sk_your_api_key_here
Content-Type: application/json

{
  "name": "example_com",
  "source_url": "https://example.com/jobs",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/jobs"],
  "rules": [],
  "settings": {"DOWNLOAD_DELAY": 1.0}
}
```

#### Update Spider
```http
PUT /api/v1/spiders/{spider_id}
Authorization: Bearer sk_your_api_key_here
Content-Type: application/json
```

#### Delete Spider
```http
DELETE /api/v1/spiders/{spider_id}
Authorization: Bearer sk_your_api_key_here
```

#### Get Spider Details
```http
GET /api/v1/spiders/{spider_name}
Authorization: Bearer sk_your_api_key_here
```

### Crawls

#### Create Crawl Run
```http
POST /api/v1/crawls
Authorization: Bearer sk_your_api_key_here
Content-Type: application/json

{
  "spider_name": "example_com",
  "project": "default",
  "requested_limit": 10,
  "output_mode": "db"
}
```

#### Get Crawl Status
```http
GET /api/v1/crawls/{crawl_run_id}
Authorization: Bearer sk_your_api_key_here
```

#### List Crawl Runs
```http
GET /api/v1/crawls?project=default&spider_name=example_com
Authorization: Bearer sk_your_api_key_here
```

### Results

#### Query Results
```http
GET /api/v1/results/{spider_name}?project=default&limit=10
Authorization: Bearer sk_your_api_key_here
```

## Rate Limiting

API requests are rate-limited using Redis:

- **Default**: 100 requests per minute per API key
- **Rate limit headers** are included in responses:
  - `X-RateLimit-Limit`: Maximum requests allowed
  - `X-RateLimit-Remaining`: Requests remaining in current window
  - `X-RateLimit-Reset`: Unix timestamp when the rate limit resets

## Webhooks

### Create Webhook Subscription

```http
POST /api/v1/webhooks
Authorization: Bearer sk_your_api_key_here
Content-Type: application/json

{
  "target_url": "https://your-app.com/webhooks/scrapai",
  "event_types": ["crawl.completed", "crawl.failed"],
  "project": "default"
}
```

### Webhook Payload

```json
{
  "event_type": "crawl.completed",
  "timestamp": "2026-03-08T12:00:00Z",
  "data": {
    "crawl_run_id": 123,
    "spider_name": "example_com",
    "project": "default",
    "items_scraped": 50,
    "duration_seconds": 120
  }
}
```

### Webhook Security

Webhooks include:
- **HMAC signature** in `X-Webhook-Signature` header (SHA256)
- **Timestamp** in `X-Webhook-Timestamp` header
- **Event type** in `X-Webhook-Event` header

Verify webhooks using your webhook secret:

```python
import hmac
import hashlib

signature = hmac.new(
    webhook_secret.encode(),
    payload.encode(),
    hashlib.sha256
).hexdigest()

# Compare with X-Webhook-Signature header
```

## Background Jobs

ScrapAI uses Dramatiq for background job processing:

### Starting Workers

```bash
# Start worker for crawl jobs
dramatiq api.workers.crawl_worker

# Start worker for webhook delivery
dramatiq api.workers.webhook_worker

# Start all workers
dramatiq api.workers
```

### Queue Names

Jobs are organized into namespaced queues:
- `joinremotes:scrapai:prod:queue:crawl` - Crawl execution
- `joinremotes:scrapai:prod:queue:webhook` - Webhook delivery
- `joinremotes:scrapai:prod:queue:validation` - Data validation

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│   FastAPI App   │
│   (api/main.py) │
└────┬─────┬──────┘
     │     │
     ▼     ▼
┌────┴─────┴──────┐    ┌─────────────┐
│ Service Layer   │────│  PostgreSQL │
│ (services/*.py) │    └─────────────┘
└────┬─────┬──────┘
     │     │
     ▼     ▼
┌────┴─────┴──────┐    ┌─────────────┐
│ Dramatiq Workers│────│    Redis    │
│ (workers/*.py)  │    └─────────────┘
└─────────────────┘
```

## Error Handling

API errors follow this format:

```json
{
  "detail": "Error message here",
  "status_code": 400
}
```

Common status codes:
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (invalid/missing API key)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error

## Testing

Run API tests:

```bash
python tests/test_api.py
```

## Production Deployment

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Using Systemd

```ini
[Unit]
Description=ScrapAI API
After=network.target

[Service]
Type=simple
User=scrapai
WorkingDirectory=/opt/scrapai
ExecStart=/opt/scrapai/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

### Using Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name api.scrapai.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

### Metrics

ScrapAI exposes basic metrics at `/metrics` (requires monitoring setup):

337: - Request count
338: - Response times
339: - Error rates
340: - Active crawl runs
341: - Queue depths
342

343: ## Server-Sent Events (SSE)
344
345
ScrapAI uses SSE for real-time crawl progress updates (simpler than WebSockets).
346
347
### Endpoint
348
349
```
350 GET /api/v1/crawls/{crawl_run_id}/stream
351 Authorization: Bearer sk_your_api_key_here
352 ```
353
354 ### Event Format
355
356
```json
357 event: crawl:started
358 data: {"status": "running", "spider_name": "example_com", "project": "default"}
359
360 event: crawl:progress
361 data: {"status": "running", "items_scraped": 25, "crawl_run_id": 123}
362
363 event: crawl:completed
364 data: {"status": "completed", "items_scraped": 50, "duration_seconds": 120}
365
366 event: crawl:failed
367 data: {"status": "failed", "error_message": "Connection timeout"}
368 ```
369
370 ### JavaScript Client Example
371
372
```javascript
373 const crawlRunId = 123;
374 const eventSource = new EventSource('/api/v1/crawls/' + crawlRunId + '/stream');
375
376 eventSource.onmessage = (event) => {
377   const data = JSON.parse(event.data);
378   console.log('Event:', event.type);
379   console.log('Data:', data);
380
381   if (data.status === 'completed' || data.status === 'failed') {
382     eventSource.close();
383   }
384 };
385
386 eventSource.onerror = (error) => {
387   console.error('SSE Error:', error);
388 };
389 ```
390
391 ### Python Client Example
392
393
```python
394 import httpx
395 import json
396
397 async def stream_crawl_progress(crawl_run_id: int):
398     async with httpx.Client() as client:
399         async with client.stream(
400             "GET",
401             f"http://localhost:8000/api/v1/crawls/{crawl_run_id}/stream",
402             headers={"Authorization": "Bearer sk_your_api_key_here"},
403         ) as response:
404             async for line in response.aiter_text():
405                 if line.startswith("data:"):
406                     data = json.loads(line[5:].strip())
407                     print(f"Event: {data}")
408                     if data.get("status") in ["completed", "failed", "cancelled"]:
409                         break
410
411
412 await stream_crawl_progress(123)
413 ```
414
415 ### curl Example
416
417
```bash
418 curl -N -H "Authorization: Bearer sk_your_api_key_here" \
419   http://localhost:8000/api/v1/crawls/123/stream
420 ```
421
422 ### Benefits of SSE
423
424
425
426
427
428- Simpler implementation than WebSockets
429- Works through proxies and load balancers without special configuration
430- Auto-reconnection handling
431 - Built-in browser support via `EventSource`
432
433
434
435
436
437
438
439
440
441
442
443
444
445
446
447
448
449
450
451
452
453
454
455
456
457
458
459
460
461
462
463
464
465
466
467
468
469
470
471
472
473
474
475
476
477
478
479
480
481
482
483
484
485
486
487
488
489
490
491
492
493
494
495
496
497
498
499
500
501
502
503
504
505
506
507
508
509
510
511
512
513
514
515
516
517
518
519
520
521
522
523
524
525
526
527
528
529
530
531
532
533
534
535
536
537
538
539
540
541
542
543
544
545
546
547
548
549
550
551
552
553
554
555
556
557
558
559
560
561
562
563
564
565
566
567
568
569
570
571
572
573
574
575
576
577
578
579
580
581
582
583
584
585
586
587
588
589
590
591
592
593
594
595
596
597
598
599
600
601
602
603
604
605
606
607
608
609
610
611
612
613
614
615
616
617
618
619
620
621
622
623
624
625
626
627
628
629
630
631
632
633
634
635
636
637
638
639
640
641
642
643
644
645
646
647
648
649
650
651
652
653
654
655
656
657
658
659
660
661
662
663
664
665
666
667
668
669
670
671
672
673
674
675
676
677
678
679
680
681
682
683
684
685
686
687
688
689
690
691
692
693
694
695
696
697
698
699
700
701
702
703
704
705
706
707
708
709
710
711
712
713
714
715
716
717
718
719
720
721
722
723
724
725
726
727
728
729
730
731
732
7733
734
735
736
737
738
739
740
741
742
743
744
745
746
747
748
749
750
751
752
753
754
755
756
757
758
759
760
761
762
763
764
765
766
767
768
769
770
771
772
773
774
775
776
777
778
779
780
781
782
783
784
785
786
787
788
789
790
791
792
793
794
795
796
797
798
799
800
801
802
803
804
805
806
807
808
809
810
811
812
813
814
815
816
817
818
819
820
821
822
823
824
825
826
827
828
829
830
831
832
833
834
835
836
837
838
839
840
841
842
843
844
845
846
847
848
849
850
851
852
853
854
855
856
857
858
859
860
861
862
863
864
865
866
867
868
869
870
871
872
873
874
875
876
877
878
879
880
881
882
883
884
885
886
887
888
889
890
891
892
893
894
895
896
897
898
899
900
901
902
903
904
905
906
907
908
909
910
911
912
913
914
915
916
917
918
919
920
921
922
923
924
925
926
927
928
929
930
931
932
933
934
935
936
937
938
939
940
941
942
943
944
945
946
947
948
949
950
951
952
953
954
955
956
957
958
959
960
961
962
963
964
965
966
967
968
969
970
971
972
973
974
975
976
977
978
979
980
981
982
983
984
985
986
987
988
989
990
991
992
993
994
995
996
997
998
999
1000
1001
1002
1003
1004
1005
1006
1007
1008
1009
1010
1011
1012
1013
1014
1015
1014
1015
1016
1017
1018
1019
1020
1021
1022
1023
1024
1025
1026
1027
1028
 publishing events to:
429- `crawl:init` - Initial state on crawl started
430- `crawl:started` - Crawl execution began
431- `crawl:progress` - Items scraped count updated
432- `crawl:completed` - Crawl finished successfully
433- `crawl:failed` - Crawl failed with error
434
435 ## Support
436
437 - **Documentation**: `http://localhost:8000/docs`
438 - **Issues**: GitHub Issues
439 - **Kanban Board**: Obsidian workspace at `kanban/scrapai-cli/`
