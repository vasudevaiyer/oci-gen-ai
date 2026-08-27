/* Vector table bootstrap. The optional ONNX model load remains deferred. */

CREATE TABLE product_embeddings (
    embedding_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id NUMBER NOT NULL REFERENCES products(product_id),
    embedding_model VARCHAR2(100) DEFAULT 'all_MiniLM_L12_v2',
    embedding_text CLOB,
    embedding VECTOR(384),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_prod_embed UNIQUE (product_id, embedding_model)
);

CREATE VECTOR INDEX idx_product_vec ON product_embeddings(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS WITH DISTANCE COSINE WITH TARGET ACCURACY 95;

CREATE TABLE post_embeddings (
    embedding_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    post_id NUMBER NOT NULL REFERENCES social_posts(post_id),
    embedding_model VARCHAR2(100) DEFAULT 'all_MiniLM_L12_V2',
    embedding_text CLOB,
    embedding VECTOR(384),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_post_embed UNIQUE (post_id, embedding_model)
);

CREATE VECTOR INDEX idx_post_vec ON post_embeddings(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS WITH DISTANCE COSINE WITH TARGET ACCURACY 95;

CREATE TABLE semantic_matches (
    match_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    post_id NUMBER NOT NULL REFERENCES social_posts(post_id),
    product_id NUMBER NOT NULL REFERENCES products(product_id),
    similarity_score NUMBER(6,5),
    match_rank NUMBER(4),
    match_method VARCHAR2(30) DEFAULT 'vector',
    verified NUMBER(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE INDEX idx_semantic_post ON semantic_matches(post_id);
CREATE INDEX idx_semantic_product ON semantic_matches(product_id);
CREATE INDEX idx_semantic_score ON semantic_matches(similarity_score DESC);
