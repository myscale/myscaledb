-- Tags: no-parallel

SET allow_experimental_inverted_index = true;
SET enable_brute_force_vector_search=1;

drop table if exists test_vector_invert_join;
CREATE TABLE test_vector_invert_join
(
    id UInt64,
    vector Array(Float32),
    doc String,
    INDEX inv_idx(doc) TYPE fts GRANULARITY 1,
    CONSTRAINT vector_len CHECK length(vector) = 3
)
ENGINE = MergeTree
ORDER BY id
settings index_granularity=2;

INSERT INTO test_vector_invert_join VALUES (0, [0,0,0], 'Ancient empires rise and fall, shaping history''s course.'),(1,[1,1,1], 'Artistic expressions reflect diverse cultural heritages.'),(2,[2,2,2], 'Social movements transform societies, forging new paths.'),(3,[3,3,3], 'Economies fluctuate, reflecting the complex interplay of global forces.'),(4,[4,4,4], 'Strategic military campaigns alter the balance of power.'),(5, [5,5,5], 'Quantum leaps redefine understanding of physical laws.'),(6, [6,6,6],'Chemical reactions unlock mysteries of nature.'), (7,[7,7,7], 'Philosophical debates ponder the essence of existence.'),(8,[8,8,8], 'Marriages blend traditions, celebrating love''s union.'),(9,[9,9,9], 'Explorers discover uncharted territories, expanding world maps.'),(10, [10,10,10],'Innovations in technology drive societal progress.'),(11,[11,11,11], 'Environmental conservation efforts protect Earth''s biodiversity.'),(12,[12,12,12], 'Diplomatic negotiations seek to resolve international conflicts.'),(13,[13,13,13], 'Ancient philosophies provide wisdom for modern dilemmas.'),(14,[14,14,14], 'Economic theories debate the merits of market systems.'),(15,[15,15,15], 'Military strategies evolve with technological advancements.'),(16,[16,16,16], 'Physics theories delve into the universe''s mysteries.'),(17,[17,17,17], 'Chemical compounds play crucial roles in medical breakthroughs.'),(18,[18,18,18], 'Philosophers debate ethics in the age of artificial intelligence.'),(19,[19,19,19], 'Wedding ceremonies across cultures symbolize lifelong commitment.');

ALTER TABLE test_vector_invert_join ADD VECTOR INDEX vec_ind vector TYPE FLAT;

DROP TABLE IF EXISTS t_00026;
CREATE TABLE t_00026(a int, id UInt64) engine=MergeTree ORDER BY a;
INSERT INTO t_00026 SELECT number, number FROM numbers(10);
INSERT INTO t_00026 SELECT number+10, number FROM numbers(10);

SELECT 'text search function on right joined table with alias';
SELECT t1.id, t1.a, textsearch(doc, 'Ancient') as score
FROM t_00026 as t1 JOIN test_vector_invert_join as t2 ON t1.id = t2.id
ORDER BY score DESC, t1.a
LIMIT 5;

SELECT 'hybrid search function on right joined table with alias';
SELECT t1.id, t1.a, hybridsearch('fusion_type=rsf')(vector, doc, [1.0,1,1], 'Ancient') as score
FROM t_00026 as t1 JOIN test_vector_invert_join as t2 ON t1.id = t2.id
ORDER BY score DESC, t1.a
LIMIT 5;

SELECT 'text search function on right joined table w/o alias';
SELECT t1.id, t1.a, textsearch(doc, 'Ancient') as score
FROM t_00026 as t1 JOIN test_vector_invert_join ON t1.id = test_vector_invert_join.id
ORDER BY score DESC, t1.a
LIMIT 5;

SELECT 'hybrid search function on right joined table w/o alias';
SELECT t1.id, t1.a, hybridsearch('fusion_type=rsf')(vector, doc, [1.0,1,1], 'Ancient') as score
FROM t_00026 as t1 JOIN test_vector_invert_join ON t1.id = test_vector_invert_join.id
ORDER BY score DESC, t1.a
LIMIT 5;

DROP TABLE t_00026;
DROP TABLE test_vector_invert_join;
