const {test}=require('node:test');
const assert=require('node:assert/strict');
const {imageUrl,imageCandidates}=require('./load-ts')('src/lib/searchImages.ts');

test('image candidates recover thumbnails with the original and lightboxes with the preview',()=>{
    const image={url:'https://images.example/original.jpg',thumbnailUrl:'https://images.example/thumb.jpg',alt:'Image'};
    assert.deepEqual(imageCandidates(image),[image.thumbnailUrl,image.url]);
    assert.deepEqual(imageCandidates(image,false),[image.url,image.thumbnailUrl]);
    assert.deepEqual(imageCandidates({...image,thumbnailUrl:image.url}),[image.url]);
});
test('legacy mixed-content and executable image/source URLs are rejected',()=>{
    for(const value of ['http://images.example/a.jpg','javascript:alert(1)','https://user:password@images.example/a.jpg',null,{}])assert.equal(imageUrl(value),'');
    assert.deepEqual(imageCandidates({url:'https://images.example/good.jpg',thumbnailUrl:'http://images.example/bad.jpg',alt:''}),['https://images.example/good.jpg']);
    const image='data:image/png;base64,aGVsbG8=';
    assert.equal(imageUrl(image,true),image);
    assert.equal(imageUrl(image),'');
    assert.equal(imageUrl('data:text/html;base64,aGVsbG8=',true),'');
});
