# PageIndex-Based RAG System â€“ BRD & TRD

## 1. Overall Architecture

- User uploads documents via a web UI; files are stored in S3.
- The upload API (or an S3 event) enqueues a message to SQS with document metadata.
- SQS worker(s) retrieve the message, fetch the file from S3, and run a PageIndex-style tree construction pipeline using Python libraries and an LLM.
- The resulting hierarchical tree and node contents are stored in a database for retrieval.
- A query UI uses this tree to drive reasoning-based retrieval and calls Gemini to generate answers with explicit citations back to the source document.

---

## 2. Part 1 â€“ Data Ingestion Pipeline (UI â†’ S3 â†’ SQS)

### 2.1 Business & Functional Requirements

- Allow authenticated users to upload multiple document types:
  - PDF, DOC/DOCX, TXT, `.md`, common image formats (PNG/JPEG), and code files (.py, .js, .java, .ts, etc.).
- For each upload:
  - Store the binary in S3.
  - Create a document record with metadata (owner, tenant, type, size, tags, status).
  - Trigger downstream processing by sending a message to SQS with S3 object information and metadata.

### 2.2 Technical Requirements â€“ UI / Frontend

- Provide an upload interface with:
  - File picker and drag-and-drop support.
  - Multi-file upload.
  - Inputs for document name, tags, and optional project/folder association.
- Show upload progress and final status (e.g., `Uploaded`, `Processing`, `Indexed`).
- Allow users to view a list of their documents and filter by status, type, and tags.

### 2.3 Technical Requirements â€“ Backend API

- Expose endpoints such as:
  - `POST /documents` to initiate an upload, create the document record, and return a pre-signed S3 URL.
  - `GET /documents/{id}` to return metadata and current processing status.
  - `GET /documents` to list documents for the current user/tenant with pagination and filters.
- Use JWT for authentication; integrate with an identity provider (e.g., Cognito/Auth0/Keycloak/custom IdP).
- Enforce tenant isolation and access control (users see only documents from their tenant and within their RBAC permissions).

### 2.4 Technical Requirements â€“ Storage & Messaging

- **S3**
  - Bucket structure such as: `s3://<bucket>/raw/{tenant_id}/{doc_id}/{filename}`.
  - Bucket policy restricted to backend IAM roles and controlled upload via pre-signed URLs.

- **SQS**
  - Queue: `document_ingest` (or equivalent) for ingestion jobs.
  - Message body includes at minimum:
    - `doc_id`
    - `tenant_id`
    - `s3_bucket`
    - `s3_key`
    - `content_type`
    - `file_type`
  - Configure visibility timeout and redrive policy with a dead-letter queue (DLQ) for failed jobs.

- **Triggering Pattern Options**
  - **Option A (API-driven)**: backend API writes to S3, then immediately sends a message to SQS.
  - **Option B (S3-event-driven)**: S3 upload triggers a small Lambda that validates the event and enqueues a message to SQS.

### 2.5 File-Type Normalization

- **PDF**: treated as the canonical input for long-form documents; parsed later in the worker.
- **DOC/DOCX**: converted to text or PDF on the backend (e.g., via LibreOffice headless, `python-docx`, or similar tools) before tree construction.
- **TXT / `.md` / code**:
  - Treated as text-based content.
  - For `.md`, you can directly build a hierarchy based on Markdown headings.
- **Images (PNG/JPEG/etc.)**:
  - Processed via OCR in the worker stage to extract text blocks.
  - OCR output is then fed into the same tree-construction pipeline.

---

## 3. Part 2 â€“ SQS Worker & TOC Tree Construction

### 3.1 Business & Functional Requirements

- Automatically process documents arriving via SQS and:
  - Fetch the file from S3.
  - Normalize and extract text/structure.
  - Build a hierarchical table-of-contents (TOC) style tree with section titles, ranges, and summaries.
  - Persist the tree and node contents for later query-time retrieval.
- Processing is asynchronous; users can check document status and return once indexing is complete.
- The system must handle failures gracefully and support retries.

### 3.2 Technical Requirements â€“ Worker Model

- Implement workers using one of:
  - AWS Lambda functions subscribed to the SQS queue, or
  - Containerized workers on ECS/Fargate polling SQS.
- For each SQS message:
  1. Parse and validate the message payload.
  2. Retrieve the document from S3 using `s3_bucket` and `s3_key`.
  3. Detect file type and run the appropriate extraction path:
     - PDF â†’ PDF parser.
     - DOC/DOCX â†’ convert then parse.
     - TXT/MD/Code â†’ direct text processing.
     - Image â†’ OCR then text processing.
  4. Run the PageIndex-style indexing pipeline to generate the TOC tree.
  5. Persist the resulting tree and any node contents.
  6. Update the document status (e.g., `Indexed` or `Failed`).
- Design for idempotency:
  - If a message is re-delivered, re-check document status before re-processing.

### 3.3 TOC / Tree Construction Logic

- Use open-source Python libraries for low-level parsing:
  - PDF/text extraction (e.g., `pdfplumber`, `PyMuPDF`, `pypdf`, or similar) as needed.
  - Additional helper libraries (such as TOC or layout analyzers) as desired.
- Build a PageIndex-style hierarchical tree structure:
  - **Node fields (minimum):**
    - `node_id` â€“ unique identifier within a document.
    - `title` â€“ human-readable section title.
    - `start_page` / `end_page` â€“ page indices or line ranges.
    - `children` â€“ list of child nodes (recursive structure).
    - `summary` â€“ short natural-language summary of the node content.
  - **Root-level document metadata:**
    - Overall title.
    - Optional global description.
    - Total number of pages.
- Node boundaries can be inferred using:
  - Structural cues (headings, fonts, numbering, spacing).
  - LLM-assisted reasoning over chunked page ranges.

### 3.4 LLM Usage in Indexing

- Use an LLM (e.g., Gemini, OpenAI GPT, or equivalent) within the worker to:
  - Refine or generate section titles.
  - Decide node boundaries and hierarchical relationships.
  - Summarize nodes and create an overall document description.
- Configure hyperparameters similar to PageIndex patterns:
  - `max_pages_per_node`: maximum contiguous pages per node.
  - `max_tokens_per_node`: to prevent exceeding LLM context limits.
  - Flags to control generation of summaries and document-level description.

### 3.5 Persistence Model

- Store trees in a document store or database, for example:
  - DynamoDB, MongoDB, or Postgres with JSONB columns.
- Recommended schema fields:
  - `doc_id`
  - `tenant_id`
  - `tree_json` (complete hierarchy)
  - `version`
  - `created_at` / `updated_at`
- Optional separate storage for node content:
  - Table or collection keyed by `doc_id` + `node_id` with:
    - `text_content`
    - `page_range`
    - `token_count`

### 3.6 Reliability & Error Handling

- Configure SQS DLQ for messages that fail after N retries.
- Log all processing steps and failures with sufficient metadata (doc_id, tenant_id, error type).
- Provide an admin UI (see Part 3) to inspect failed documents and optionally requeue them.

---

## 4. Part 3 â€“ UI Editor & Admin (Query, Logs, JWT, RBAC)

### 4.1 Business & Functional Requirements

- Provide a "Query UI" where users can:
  - Select a document or collection.
  - Ask natural language questions.
  - View answers with citations to specific sections/pages.
- Provide an "Index Editor" for power users/admins to:
  - Visualize the tree structure.
  - Edit node titles and hierarchy.
  - Split/merge sections and save new versions.
- Provide an Admin module to:
  - Manage users and roles.
  - View query history and system logs.
  - Monitor document ingestion and indexing status.

### 4.2 Technical Requirements â€“ Query UI

- Implement a modern SPA (React/Vue/Svelte or similar) with:
  - Left panel: document list and filters.
  - Center: conversational chat view (question/answer pairs per document or project).
  - Right panel: citations and context details.
- Key features:
  - Chat history per document or per conversation.
  - Display of citations inline with answers; clicking a citation reveals the corresponding node and page range.
  - Ability to expand nodes to view the underlying text.

### 4.3 Technical Requirements â€“ Index Editor

- Tree visualization:
  - Collapsible/expandable tree with node titles and page ranges.
  - Search box to locate nodes by title or content snippet.
- Editing capabilities:
  - Rename node titles.
  - Drag-and-drop to change node order or parent.
  - Split node (specify a new boundary, e.g., by page/line).
  - Merge nodes with adjacent siblings.
  - Save changes as a new version of the tree (with versioning metadata).

### 4.4 Technical Requirements â€“ Admin & Security (JWT, RBAC)

- Authentication:
  - Use JWT-based authentication via an IdP (Cognito/Auth0/Keycloak/custom).
  - JWT must carry `sub` (user id), `tenant_id`, and `roles`.
- RBAC:
  - Suggested roles:
    - `ADMIN`: full access to all tenant resources; can manage users and view system logs.
    - `EDITOR`: can modify document trees, metadata, and tags.
    - `VIEWER`: read-only access; can query allowed documents.
  - Enforce RBAC in the API layer for all document and admin operations.
- Admin module features:
  - User management (create/disable users, assign roles).
  - System metrics dashboard (documents processed, errors, queue depth).
  - Query history search and filtering by:
    - user
    - document
    - time range
    - outcome (success/failure/no-answer)

---

## 5. Part 4 â€“ Gemini-Based Answering with Citations

### 5.1 Business & Functional Requirements

- For each user query against one or more documents:
  - Use the stored tree index to select the most relevant nodes.
  - Call Gemini to generate an answer based solely on those nodes.
  - Return an answer with explicit citations back to the underlying sections/pages.
- Citations must be clear and useful to humans and machines, enabling traceability and auditability.

### 5.2 Technical Requirements â€“ Retrieval Workflow (Vectorless, Reasoning-Based)

- For a given query:
  1. Fetch the document's tree JSON and metadata.
  2. Run a "node selection" step with an LLM (Gemini or another reasoning model):
     - Provide the query and the tree (or a relevant subset) as input.
     - Instruct the model to return a list of relevant `node_id`s plus its reasoning.
     - Output shape example:
       ```json
       {
         "thinking": "...",
         "node_list": ["node-1", "node-5", "node-9"]
       }
       ```
  3. Fetch the content for the selected nodes from the node store.
  4. Construct a final prompt for Gemini including:
     - The user query.
     - A list of context snippets labeled by `node_id` and page range.
     - Instructions to answer using only provided context and to include citations.

### 5.3 Technical Requirements â€“ Gemini Integration

- Use Gemini API (or Vertex AI) client libraries to call a model such as:
  - `gemini-2.5-flash` for fast Q&A, or
  - `gemini-2.5-pro` for deeper reasoning as needed.
- Prompt design for citations, e.g.:
  - Instruct Gemini:
    - "When you use a specific context snippet, append a citation of the form `[CIT: node_id=<id>, pages=<start>-<end>]` at the end of the relevant sentence."
- After receiving the model output:
  - Parse citation markers.
  - Map `node_id` and page information back to:
    - tree nodes in the UI, and
    - stored page ranges.
  - Render citations in the UI as clickable chips/links that open the referenced section.

### 5.4 Answering API

- Provide a backend endpoint, for example:
  - `POST /documents/{doc_id}/query`
    - **Request body**:
      ```json
      {
        "query": "string",
        "top_k": 5,
        "conversation_id": "optional-string"
      }
      ```
    - **Response body**:
      ```json
      {
        "answer": "string",
        "citations": [
          {
            "node_id": "string",
            "page_start": 10,
            "page_end": 12,
            "snippet": "string"
          }
        ],
        "raw_model_output": {}
      }
      ```
- Optionally support multi-document queries by accepting an array of `doc_id`s and merging retrieval results.

### 5.5 Safeguards & Quality Controls

- Include guardrails in prompts such as:
  - "If the answer is not present in the provided context, clearly state that you cannot find the answer instead of guessing."
- Log retrieval decisions:
  - Selected `node_id`s, their ranking, and reasons.
  - Cases where no adequate answer was found.
- Provide feedback mechanisms in the UI so users can rate answers, flag incorrect citations, and help improve future prompts/configuration.

---

## 6. Non-Functional Requirements (Cross-Cutting)

### 6.1 Performance & Scalability

- Indexing throughput should support hundreds of pages per document on commodity infrastructure.
- Horizontal scaling of workers via Lambda concurrency or ECS tasks.
- Query latency targets:
  - Single-document Q&A typically responds within a few seconds under normal load.

### 6.2 Reliability & Resilience

- Use SQS DLQs and retry policies for robust ingestion.
- Implement health checks for worker pools and key services.
- Monitor error rates, queue depth, and processing times; alert on anomalies.

### 6.3 Security & Compliance

- Enforce strict IAM policies around S3, SQS, and databases.
- Ensure all external LLM calls comply with your org's data-handling policies.
- Support per-tenant data isolation and access controls via JWT and RBAC.

### 6.4 Observability

- Centralize logs (e.g., CloudWatch/ELK/OpenSearch) with correlation IDs for each document and request.
- Collect metrics:
  - Documents uploaded, indexed, failed.
  - Queue depth and worker throughput.
  - LLM token usage and latency.
- Provide dashboards for operations and admin users.