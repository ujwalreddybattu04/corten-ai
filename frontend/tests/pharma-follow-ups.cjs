const { test } = require('node:test');
const assert = require('node:assert/strict');
const { pharmaFollowUps, pharmaQuestionKey } = require('./load-ts')('src/lib/pharmaFollowUps.ts', new Map());
const turn = (query, answer = 'The requested information was retrieved.') => ({ query, answer, sources: [] });
function record(source = 'ema') {
    return { item: { source, title: 'Revatio · Post-authorisation decision', organization: 'Pfizer',
        details: { ingredients: ['sildenafil'], ema_product_number: 'EMEA/H/C/000638', latest_procedure: 'VR/0000386049' }, drugs: [] }, feed: {} };
}
test('EMA suggestions target the actual product, procedure and correct regulator', () => {
    const questions = pharmaFollowUps(record(), [turn('Automatic brief', 'The changes are not detailed in this record.')]);
    assert.equal(questions.length, 3);
    assert.ok(questions[0].includes('Revatio, procedure VR/0000386049'));
    assert.ok(questions.some(q => q.includes('EMA product information')));
    assert.ok(!questions.some(q => q.includes('original regulatory record establish')));
});
test('asked prompts and paraphrases are excluded across a multi-turn conversation', () => {
    const r = record(), history = [turn('Automatic brief')];
    const first = pharmaFollowUps(r, history);
    history.push(turn(first[0]));
    const second = pharmaFollowUps(r, history);
    assert.ok(!second.includes(first[0]));
    assert.ok(!second.some(q => q.includes('assessment documents')));
    history.push(turn('Could you show me the current product information for Revatio?'));
    assert.ok(!pharmaFollowUps(r, history).some(q => q.includes('product information')));
});
test('combined questions consume both topics and saved history gives the same suggestions', () => {
    const r = record(), history = [turn('Automatic brief'), turn('Find current labeling and clinical evidence for sildenafil.')];
    const questions = pharmaFollowUps(r, history);
    assert.ok(!questions.some(q => /product information|published clinical evidence/.test(q)));
    assert.deepEqual(pharmaFollowUps(r, JSON.parse(JSON.stringify(history))), questions);
});
test('a new question changes the next-step priorities rather than serving the same record menu', () => {
    const r = record(), first = [turn('Brief')];
    const questions = pharmaFollowUps(r, [...first, turn('What safety warnings apply to sildenafil?')]);
    assert.ok(questions[0].includes('published clinical evidence'));
    assert.notDeepEqual(questions, pharmaFollowUps(r, first));
});
test('trial suggestions use the exact identifier and do not assume missing results exist', () => {
    const r = record('trials');r.item.details = { study_id: 'NCT12345678', interventions: ['Example drug'] };
    let questions = pharmaFollowUps(r, [turn('Brief')]);
    assert.ok(questions[0].startsWith('Check whether results'));
    assert.ok(questions.every(q => !q.includes('undefined')));
    r.item.details.results_posted = '2026-10-01';
    questions = pharmaFollowUps(r, [turn('Brief'), turn('Are any trial results posted?')]);
    assert.ok(!questions.some(q => /results/.test(q)));
    assert.ok(questions.some(q => /endpoints/.test(q)));
});
test('exhausted suggestions disappear instead of recycling answered topics', () => {
    const r = record(), history = [turn('Brief')];
    for (let n = 0; n < 8; n++) {
        const [question] = pharmaFollowUps(r, history);
        if (!question) break;
        history.push(turn(question));
    }
    assert.deepEqual(pharmaFollowUps(r, history), []);
});
test('question identity preserves non-English names and normalizes punctuation and case', () => {
    assert.equal(pharmaQuestionKey('  FIND EMA\u200b documents for Révatio?'), pharmaQuestionKey('find ema documents for Révatio.'));
    assert.notEqual(pharmaQuestionKey('药物甲'), pharmaQuestionKey('药物乙'));
});
