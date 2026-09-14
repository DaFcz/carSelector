# Car Selector Roles

This is not only a software project but a complete **AI product with data acquisition, recommendation engine, cloud hosting, operations, and continuous improvement**.

For an end-to-end delivery, I would split responsibilities into the following roles.

---

# Leadership & Product

## 1. Product Owner (PO)

**Mission:** Own the vision and business value.

### Responsibilities

- Define MVP and roadmap
- Prioritize features
- Validate user journeys
- Manage stakeholders
- Decide release scope

### Deliverables

- Product backlog
- Acceptance criteria
- Release plan

---

## 2. Solution Architect

**Mission:** Design the whole platform.

### Responsibilities

- Define architecture
- Decide technology stack
- API design
- Security strategy
- Scalability planning

### Deliverables

- Architecture diagrams
- Technology decisions
- Technical standards

---

# Data Acquisition Layer

## 3. Vehicle Data Lead

**Mission:** Own vehicle information quality.

### Responsibilities

- Define vehicle schema
- Standardize parameters
- Data normalization
- Taxonomy management

### Deliverables

- Vehicle data model
- Data dictionaries
- Data quality rules

---

## 4. Web Scraping Engineer

**Mission:** Collect vehicle manuals and price lists.

### Responsibilities

- Develop scrapers
- Lazy scraping strategy
- PDF extraction
- Price-list parsing
- Source monitoring

### Deliverables

- Scraping pipelines
- Data extraction framework
- Source quality reports

---

## 5. Document Processing & RAG Engineer

**Mission:** Convert manuals into searchable knowledge.

### Responsibilities

- PDF parsing
- OCR when needed
- Embedding generation
- Vector database maintenance
- Retrieval optimization

### Deliverables

- Knowledge base
- Chunking strategy
- RAG pipelines

---

# AI & Recommendation

## 6. AI/LLM Engineer

**Mission:** Build the conversational assistant.

### Responsibilities

- Prompt engineering
- Requirement extraction
- Follow-up questioning
- Function calling
- LLM evaluation

### Deliverables

- Chat workflows
- Prompt library
- AI evaluation metrics

---

## 7. Recommendation Engine Engineer

**Mission:** Match customer needs to vehicles.

### Responsibilities

- Scoring algorithms
- Ranking strategy
- Feature weighting
- Explainable recommendations

### Deliverables

- Recommendation service
- Scoring model
- Explanation engine

---

## 8. Data Scientist (Optional Advanced Role)

**Mission:** Improve recommendations using analytics.

### Responsibilities

- User behavior analysis
- Personalization
- Recommendation tuning
- A/B testing

### Deliverables

- Recommendation improvements
- Analytics reports

---

# Backend

## 9. Backend Lead

**Mission:** Own APIs and business logic.

### Responsibilities

- FastAPI services
- Database design
- Authentication
- Integration endpoints

### Deliverables

- REST APIs
- Swagger/OpenAPI
- Service architecture

---

## 10. Database Engineer

**Mission:** Maintain vehicle and user data.

### Responsibilities

- PostgreSQL administration
- Query optimization
- Backup strategy
- Database migrations

### Deliverables

- DB schema
- Index strategy
- Backup procedures

---

# Frontend

## 11. Frontend Lead

**Mission:** Build customer experience.

### Responsibilities

- React frontend
- Vehicle search screens
- Comparison interface
- Responsive design

### Deliverables

- Web application
- Component library
- User experience standards

---

## 12. UX/UI Designer

**Mission:** Make recommendations understandable.

### Responsibilities

- User journeys
- Wireframes
- Visual design
- Usability testing

### Deliverables

- Mockups
- Design system
- User flow diagrams

---

# DevOps & Hosting

## 13. DevOps Engineer

**Mission:** Deploy and operate the platform.

### Responsibilities

- Docker
- CI/CD
- Cloud deployment
- Monitoring

### Deliverables

- GitHub Actions
- Infrastructure setup
- Release pipeline

---

## 14. Cloud Infrastructure Engineer

**Mission:** Optimize hosting costs.

### Responsibilities

- Cloud architecture
- Cost monitoring
- Scaling strategy
- Security hardening

### Deliverables

- Hosting architecture
- Cost reports
- Disaster recovery plan

---

# Quality & Operations

## 15. QA/Test Engineer

**Mission:** Ensure reliability.

### Responsibilities

- Manual testing
- API tests
- Regression tests
- AI evaluation tests

### Deliverables

- Test plans
- Automated test suites
- Quality metrics

---

## 16. Security & Compliance Engineer

**Mission:** Protect users and data.

### Responsibilities

- Security assessment
- GDPR compliance
- Authentication strategy
- Penetration testing

### Deliverables

- Security checklist
- Privacy policies
- Risk assessment

---

# Business & Growth

## 17. Analytics & SEO Specialist

**Mission:** Bring traffic and measure success.

### Responsibilities

- SEO optimization
- Google Analytics
- Conversion tracking
- User behavior analysis

### Deliverables

- SEO strategy
- KPI dashboards

---

## 18. Customer Success / Operations Owner

**Mission:** Operate platform post-launch.

### Responsibilities

- Handle feedback
- Support users
- Manage vehicle data freshness
- Prioritize improvements

### Deliverables

- Support processes
- Improvement backlog

---

# Recommended Team Size

## Small MVP Team (5–7 people)

- Product Owner
- Solution Architect (also Backend Lead)
- AI/LLM Engineer
- Web Scraping + RAG Engineer
- Frontend Developer
- DevOps Engineer
- QA (part-time)

---

## Serious Production Team (10–12 people)

- Product Owner
- Solution Architect
- Backend Lead
- AI/LLM Engineer
- Recommendation Engineer
- Scraping Engineer
- RAG Engineer
- Frontend Lead
- UX/UI Designer
- DevOps Engineer
- QA Engineer
- Analytics/SEO Specialist

---

# Cost-Effective Hosting Recommendation

## For a Startup / MVP

### Frontend

- Cloudflare Pages (free)

### Backend

- Railway or Render (€5–20/month)

### PostgreSQL

- Supabase (free tier initially)

### Vector DB

- Qdrant Cloud free tier

### Storage

- Cloudflare R2

### CI/CD

- GitHub Actions

### LLM

- OpenAI API for best quality
- Azure OpenAI for enterprise
- Ollama + Llama 3 if very cost-sensitive

### Expected MVP Operating Cost

- Development: €0–20/month
- Production MVP: €30–100/month
- Growing audience: €100–500/month depending largely on LLM usage

---

# Additional Recommended Role

## Vehicle Knowledge Curator

Many teams forget this role.

### Responsible For

- Validating scraped vehicle data
- Verifying extracted specifications
- Checking model-year changes
- Ensuring recommendation quality

This role significantly increases trust in the final recommendations and often determines whether users perceive the platform as "expert-level" or not.

---

# Role Assignment

| Person | Assignment |
|----------|------------|
| Martin Kolá | Web scraping, document processing |
| Jan Pikryl | Backend Lead |
| Dušan Juhás | Frontend Lead |
| Daniel Fritz | DevOps Engineer |

