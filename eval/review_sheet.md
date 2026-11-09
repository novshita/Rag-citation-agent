# Review sheet for the evaluation questions

A local aid for checking `eval/questions.json` (not part of the project; don't commit it).

**How to use it:** for each question, open the linked source file, find the passage, and tick the box if the expected answer is right.
For the *unanswerable* questions the check is the opposite: confirm the documents really do **not** answer it. The counts show how often the key words appear in the corpus.

Tip: in VS Code, open the source file and use Cmd+F to search for a key word from the expected answer.

---

## Single questions

### s01  (test split)
**Question:** Which method do you call on the BackgroundTasks object to schedule a function?

**Expected answer:** The .add_task() method, passing the task function followed by its positional and keyword arguments.

**Check it against:** [tutorial/background-tasks.md](../data/raw/tutorial/background-tasks.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s02  (dev split)
**Question:** Can a background task function be declared with async def, or must it be a normal def?

**Expected answer:** Either: it can be an async def or a normal def function and FastAPI handles both.

**Check it against:** [tutorial/background-tasks.md](../data/raw/tutorial/background-tasks.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s03  (test split)
**Question:** When should I use a tool like Celery instead of FastAPI's BackgroundTasks?

**Expected answer:** For heavy background computation that doesn't need to run in the same process (no shared memory or variables), especially across multiple processes or servers; BackgroundTasks is fine for small tasks like sending an email.

**Check it against:** [tutorial/background-tasks.md](../data/raw/tutorial/background-tasks.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s04  (test split)
**Question:** What status code and JSON body does the client get when the code raises HTTPException with a 404 and detail 'Item not found'?

**Expected answer:** Status 404 with the JSON body {"detail": "Item not found"}.

**Check it against:** [tutorial/handling-errors.md](../data/raw/tutorial/handling-errors.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s05  (test split)
**Question:** Which Python package must be installed to receive uploaded files?

**Expected answer:** python-multipart, because uploaded files are sent as form data.

**Check it against:** [tutorial/request-files.md](../data/raw/tutorial/request-files.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s06  (dev split)
**Question:** What does the filename attribute of UploadFile contain?

**Expected answer:** A str with the original file name that was uploaded, e.g. myimage.jpg.

**Check it against:** [tutorial/request-files.md](../data/raw/tutorial/request-files.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s07  (test split)
**Question:** Why is UploadFile better than declaring a file parameter as bytes for large files?

**Expected answer:** UploadFile uses a spooled file: it is kept in memory up to a size limit and then stored on disk, so large files like images or videos don't consume all the memory, whereas bytes keeps the whole content in memory.

**Check it against:** [tutorial/request-files.md](../data/raw/tutorial/request-files.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s08  (test split)
**Question:** In a lifespan function, what runs before the yield and what runs after it?

**Expected answer:** The code before the yield runs at startup, before the application starts receiving requests; the code after the yield runs at shutdown, after it has finished handling requests, e.g. to release resources.

**Check it against:** [advanced/events.md](../data/raw/advanced/events.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s09  (test split)
**Question:** Which approach is recommended for startup and shutdown logic, the lifespan parameter or startup/shutdown event handlers?

**Expected answer:** The lifespan parameter. If you provide a lifespan parameter, the startup and shutdown event handlers are no longer called.

**Check it against:** [advanced/events.md](../data/raw/advanced/events.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s10  (test split)
**Question:** Do lifespan events run for mounted sub applications?

**Expected answer:** No. Lifespan events (startup and shutdown) are only executed for the main application, not for sub applications (mounts).

**Check it against:** [advanced/events.md](../data/raw/advanced/events.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s11  (test split)
**Question:** Which command line option starts several Uvicorn worker processes with the fastapi command?

**Expected answer:** The --workers option, for example fastapi run --workers 4 main.py.

**Check it against:** [deployment/server-workers.md](../data/raw/deployment/server-workers.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s12  (test split)
**Question:** What does the --forwarded-allow-ips option do?

**Expected answer:** It tells the FastAPI CLI server which IP addresses to trust for reading the proxy forwarded headers (X-Forwarded-For, -Proto, -Host); "*" trusts all incoming IPs.

**Check it against:** [advanced/behind-a-proxy.md](../data/raw/advanced/behind-a-proxy.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s13  (dev split)
**Question:** Why must the /users/me path operation be declared before /users/{user_id}?

**Expected answer:** Path operations are evaluated in order, so otherwise /users/{user_id} would also match /users/me and treat "me" as the user_id value.

**Check it against:** [tutorial/path-params.md](../data/raw/tutorial/path-params.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s14  (test split)
**Question:** Why is the get_settings dependency decorated with @lru_cache?

**Expected answer:** So the Settings object is created only once, on the first call, instead of being created (and the .env file read from disk) on every request.

**Check it against:** [advanced/settings.md](../data/raw/advanced/settings.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### s15  (test split)
**Question:** In FastAPI tests using TestClient, should the test functions be async def?

**Expected answer:** No. The test functions are normal def and the client calls are normal calls without await, so pytest can be used directly.

**Check it against:** [tutorial/testing.md](../data/raw/tutorial/testing.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

## Multi questions

### m01  (test split)
**Question:** Should I start my app with --workers when deploying on Kubernetes?

**Expected answer:** Usually not. On Kubernetes you would normally run a single Uvicorn process per container and let the cluster handle replication of containers, instead of using workers.

**Check it against:** [deployment/server-workers.md](../data/raw/deployment/server-workers.md), [deployment/docker.md](../data/raw/deployment/docker.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### m02  (test split)
**Question:** When a TLS termination proxy handles HTTPS in front of my app, how does the app learn the original protocol and host?

**Expected answer:** The proxy decrypts HTTPS and talks plain HTTP to the app server, adding forwarded headers (X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host) with the original details. The server only trusts them if started with --forwarded-allow-ips, which lets it e.g. generate correct https redirects.

**Check it against:** [deployment/https.md](../data/raw/deployment/https.md), [advanced/behind-a-proxy.md](../data/raw/advanced/behind-a-proxy.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### m03  (dev split)
**Question:** If I run several workers, which deployment concepts do I still have to handle myself?

**Expected answer:** Workers mainly help with replication (and a little with restarts). You still need to take care of HTTPS, running on startup, restarts, memory, and previous steps before starting.

**Check it against:** [deployment/server-workers.md](../data/raw/deployment/server-workers.md), [deployment/concepts.md](../data/raw/deployment/concepts.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### m04  (test split)
**Question:** How should I run database migrations before starting my app when I have multiple containers?

**Expected answer:** Run them once, in a single separate container/process before the replicated worker containers start (on Kubernetes, an Init Container), so multiple processes don't duplicate the work or conflict.

**Check it against:** [deployment/concepts.md](../data/raw/deployment/concepts.md), [deployment/docker.md](../data/raw/deployment/docker.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### m05  (test split)
**Question:** Which exception do I raise for an HTTP error in a normal endpoint, and which one in a WebSocket endpoint?

**Expected answer:** HTTPException for normal path operations; in a WebSocket it doesn't make sense to raise HTTPException, so raise WebSocketException with a valid closing code.

**Check it against:** [tutorial/handling-errors.md](../data/raw/tutorial/handling-errors.md), [advanced/websockets.md](../data/raw/advanced/websockets.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### m06  (test split)
**Question:** How can I make my app restart automatically after a crash, with and without containers?

**Expected answer:** Without containers use an external component in charge of restarting it, such as Systemd or Supervisor. With containers the tool running them usually has an option for it, e.g. --restart in Docker.

**Check it against:** [deployment/concepts.md](../data/raw/deployment/concepts.md), [deployment/docker.md](../data/raw/deployment/docker.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### m07  (test split)
**Question:** How does the SQL tutorial create the database tables, and what is recommended for production?

**Expected answer:** It creates them in an application startup event; for production you would use a migration script that runs before starting the app. (The startup event approach is the older one; lifespan is now recommended.)

**Check it against:** [tutorial/sql-databases.md](../data/raw/tutorial/sql-databases.md), [advanced/events.md](../data/raw/advanced/events.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### m08  (test split)
**Question:** How do I run FastAPI in a Docker container behind a proxy like Traefik so redirects use the right URL?

**Expected answer:** Add the proxy headers option to the fastapi run command in the Dockerfile CMD (e.g. --proxy-headers), so the server interprets the X-Forwarded-* headers set by the proxy; behind-a-proxy also explains trusting the proxy with --forwarded-allow-ips.

**Check it against:** [deployment/docker.md](../data/raw/deployment/docker.md), [advanced/behind-a-proxy.md](../data/raw/advanced/behind-a-proxy.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

## Adversarial questions  (false premise or near-miss)

### a01  (test split)
**Question:** Why do the docs say to return an HTTPException from the path operation function to send an error?

**Expected answer:** That's backwards: HTTPException is a Python exception, so you raise it, you don't return it. Raising it also stops the rest of the code from running.

**Check it against:** [tutorial/handling-errors.md](../data/raw/tutorial/handling-errors.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### a02  (test split)
**Question:** Why does FastAPI recommend startup and shutdown event handlers over the lifespan parameter?

**Expected answer:** It doesn't: lifespan is the recommended way, and startup/shutdown event handlers are the deprecated alternative.

**Check it against:** [advanced/events.md](../data/raw/advanced/events.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### a03  (test split)
**Question:** The Dockerfile uses pip install --no-cache-dir to enable Docker's layer cache, how does that work?

**Expected answer:** It doesn't: --no-cache-dir only tells pip not to save downloaded packages locally and has nothing to do with Docker's cache. Docker's layer cache works because requirements.txt is copied in its own step before the app code.

**Check it against:** [deployment/docker.md](../data/raw/deployment/docker.md)

- [ ] The expected answer is correct and fully supported by the source
- [ ] The answer isn't also contradicted elsewhere in the corpus

### a04  (test split)
**Question:** How do I change the compression level of FastAPI's GZip middleware?

**Expected:** the documents do not answer this.

- Key word `gzip`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### a05  (test split)
**Question:** What is the default maximum upload size FastAPI enforces for UploadFile?

**Expected:** the documents do not answer this.

- Key word `upload size`: not in the corpus
- Key word `max size`: not in the corpus
- Key word `maximum size`: appears in `data/raw/tutorial/request-files.md` (1x)
- Key word `file size`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

## Unanswerable questions

### u01  (dev split)
**Question:** How do I configure Django migrations?

**Expected:** the documents do not answer this.

- Key word `django`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u02  (dev split)
**Question:** How do I add rate limiting to a FastAPI endpoint?

**Expected:** the documents do not answer this.

- Key word `rate limit`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u03  (dev split)
**Question:** How do I implement JWT token authentication in FastAPI?

**Expected:** the documents do not answer this.

- Key word `jwt`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u04  (dev split)
**Question:** How do I set up a GitHub Actions workflow to deploy a FastAPI app?

**Expected:** the documents do not answer this.

- Key word `github actions`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u05  (test split)
**Question:** How do I deploy a FastAPI app to AWS Lambda?

**Expected:** the documents do not answer this.

- Key word `lambda`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u06  (test split)
**Question:** How do I add pagination to a list endpoint?

**Expected:** the documents do not answer this.

- Key word `pagination`: not in the corpus
- Key word `paginate`: appears in `data/raw/tutorial/sql-databases.md` (1x)

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u07  (test split)
**Question:** How do I render HTML pages with Jinja2 templates?

**Expected:** the documents do not answer this.

- Key word `jinja`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u08  (test split)
**Question:** How do I set a request timeout for FastAPI endpoints?

**Expected:** the documents do not answer this.

- Key word `timeout`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u09  (test split)
**Question:** How do I expose Prometheus metrics from a FastAPI app?

**Expected:** the documents do not answer this.

- Key word `prometheus`: not in the corpus

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)

### u10  (test split)
**Question:** How do I configure Celery workers and a RabbitMQ broker for my FastAPI app?

**Expected:** the documents do not answer this.

- Key word `celery`: appears in `data/raw/tutorial/background-tasks.md` (1x)
- Key word `rabbitmq`: appears in `data/raw/tutorial/background-tasks.md` (1x)

- [ ] Confirmed: the corpus doesn't contain an answer (a passing mention is OK)
