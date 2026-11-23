# Changelog

## [2.0.3](https://github.com/7K-Hiroba/workflows/compare/v2.0.0...v2.0.3) (2026-11-23)


### Recovery context

* v2.0.0 remains published but quarantined; v2.0.1 and v2.0.2 remain unpublished, quarantined, and unadopted. No v1/v2 alias or consumer adoption is authorized by this candidate.
* v2.0.2 was never tagged and no GitHub Release was created. Its five full rehearsals passed at `1ae0c537a525e9375d6d6d850eca7cc932c749e2`, but standalone chart run [45274871189](https://github.com/7K-Hiroba/workflows/actions/runs/45274871189) failed evidence verification on concatenated Cosign JSON documents after exactly reproducing chart digest `sha256:44170dc3b2f4afe267b2e03e948f7c54c72b22c04acce9ede3603ef281bccb99`.
* This v2.0.3 candidate includes the reviewed all-member JSON-stream verification fix from #48. The #48 merge commit `43ae83163c6bb58ef4d342dde9ec9c4bd8fdf53c` is not a qualification R. R must be this corrected Release PR's merge commit after independent review and strict checks, followed by the complete local and sequential five-full-plus-standalone matrix at that unchanged R before protected signing.

### ⚠ BREAKING CHANGES

* consumers adopting workflows v2.0.0 must migrate to inari.hiroba.app.v2 and explicitly select archetype stack or non-stack. Stacks must declare and pass install plus same-cluster upgrade lifecycle coverage; consumers not yet migrating must retain their immutable v1.1.0 pin.

### Features

* add v2 observability producer contract ([#31](https://github.com/7K-Hiroba/workflows/issues/31)) ([7ecf629](https://github.com/7K-Hiroba/workflows/commit/7ecf629dd02c9acca82878c6487a3560025e0411))
* add workflows v1 and trusted publishing ([#1](https://github.com/7K-Hiroba/workflows/issues/1)) ([78b2e66](https://github.com/7K-Hiroba/workflows/commit/78b2e662bc414aa231cf640e9f17168adaa66b53))
* standardize classified stack testing ([#39](https://github.com/7K-Hiroba/workflows/issues/39)) ([7e61f10](https://github.com/7K-Hiroba/workflows/commit/7e61f10f1f78ebf9470a6f9343dd86d71e4e6447))
* support full-matrix Hiroba scaffolds ([3406716](https://github.com/7K-Hiroba/workflows/commit/340671634ca6ea56fbeca54bacd7e18f5135c49b))
* support full-matrix release identities ([#37](https://github.com/7K-Hiroba/workflows/issues/37)) ([0c491e8](https://github.com/7K-Hiroba/workflows/commit/0c491e8811bc2b9688f8bb2a3eb6079fad955506))
* support Mimir observability assets ([#38](https://github.com/7K-Hiroba/workflows/issues/38)) ([ba015f6](https://github.com/7K-Hiroba/workflows/commit/ba015f62e5b5ab4cfccd01e5468bbfb26a9ac2ae))


### Bug Fixes

* allow optional Helm manifest media type ([26eb586](https://github.com/7K-Hiroba/workflows/commit/26eb58679a590c13f9bdc71156494f1f8765e585))
* allow optional Helm manifest media type ([39481a0](https://github.com/7K-Hiroba/workflows/commit/39481a08747c739efd3a8daa62c1c4adb78dfb78))
* assemble canonical template evidence filenames ([95aa59c](https://github.com/7K-Hiroba/workflows/commit/95aa59c67d94551bcab6dff963ce9339a7bfdabf))
* assemble canonical template evidence filenames ([de4360a](https://github.com/7K-Hiroba/workflows/commit/de4360affab03d9e9da84c23a604162186a35c61))
* authenticate chart crane reads ([bb4a1ca](https://github.com/7K-Hiroba/workflows/commit/bb4a1ca92e079af5bfa06f6acd739f19e49a9e57))
* complete release permission chain ([#4](https://github.com/7K-Hiroba/workflows/issues/4)) ([fa01f9a](https://github.com/7K-Hiroba/workflows/commit/fa01f9aa41f8536f876c91b4f9935c7041b7d624))
* consume aggregated chart stack evidence ([#43](https://github.com/7K-Hiroba/workflows/issues/43)) ([ee2ec5a](https://github.com/7K-Hiroba/workflows/commit/ee2ec5ab5724b8e24f6eb65d9e43f1658f20a087))
* create GitHub release inside consumer repository ([8f9bb9f](https://github.com/7K-Hiroba/workflows/commit/8f9bb9f4b42b4a7a6a7ab327e38c9a0a8cc21c22))
* create GitHub release inside consumer repository ([0813e95](https://github.com/7K-Hiroba/workflows/commit/0813e9542c6347e174019d7f406c75b06038c220))
* create release evidence directory before runtime copy ([7bc0b00](https://github.com/7K-Hiroba/workflows/commit/7bc0b003994714c5e85f75bbd1afc1db969461c8))
* default fixture runtime evidence to ineligible ([#35](https://github.com/7K-Hiroba/workflows/issues/35)) ([f92f591](https://github.com/7K-Hiroba/workflows/commit/f92f591ca6eb515b46b3b6d284b739a5011aff99))
* export release source SHA with valid shell name ([3e61ce5](https://github.com/7K-Hiroba/workflows/commit/3e61ce5441e3176b10dc1029a3106e23f22ad752))
* export release source SHA with valid shell name ([314ace0](https://github.com/7K-Hiroba/workflows/commit/314ace08ae30f3e76bc05299602a96df32c72c4a))
* grant artifact metadata writes to attestation jobs ([#32](https://github.com/7K-Hiroba/workflows/issues/32)) ([e9f81b3](https://github.com/7K-Hiroba/workflows/commit/e9f81b3d9250cc67f7e0c69772eb1a3840b8c0db))
* grant full rehearsal nested contents write ([#3](https://github.com/7K-Hiroba/workflows/issues/3)) ([f07f695](https://github.com/7K-Hiroba/workflows/commit/f07f6959a5afc3528fe334b4f9484349f47e616e))
* make chart packaging reproducible ([#45](https://github.com/7K-Hiroba/workflows/issues/45)) ([3883213](https://github.com/7K-Hiroba/workflows/commit/388321348b6886c3e1675cfcb0190ffd5ee49c40))
* normalize setup-node cache paths ([#41](https://github.com/7K-Hiroba/workflows/issues/41)) ([4208216](https://github.com/7K-Hiroba/workflows/commit/420821655637244e1b14826de2188e4d657c5fb5))
* preserve compatibility evidence layout ([a7300a7](https://github.com/7K-Hiroba/workflows/commit/a7300a7fa2e649813c19f7c12273ebbcffca1b4c))
* preserve compatibility evidence layout ([12a0ede](https://github.com/7K-Hiroba/workflows/commit/12a0edef25d6f8ddedf1c99161848b98f17f92df))
* provide token to release verification ([2d5adf6](https://github.com/7K-Hiroba/workflows/commit/2d5adf649707d3ba50b355f8666ec2c8396223a9))
* provide token to release verification ([14e0ec8](https://github.com/7K-Hiroba/workflows/commit/14e0ec8e6ec6af30a9ec7d92d4e2594c4e5b4fbc))
* publish chartless rehearsal package chain ([#33](https://github.com/7K-Hiroba/workflows/issues/33)) ([c3bdc1e](https://github.com/7K-Hiroba/workflows/commit/c3bdc1e715391a8c66d599ce32356e6ea071e169))
* push backend from OCI layout ([3385a71](https://github.com/7K-Hiroba/workflows/commit/3385a71c2e9a8d61c6b4ab37932145b828df8928))
* resolve rehearsal publish failures ([b33284d](https://github.com/7K-Hiroba/workflows/commit/b33284d36ff2b65bb05c288129fdfe8f62bed09a))
* separate non-plugin package release identity ([#34](https://github.com/7K-Hiroba/workflows/issues/34)) ([265b13e](https://github.com/7K-Hiroba/workflows/commit/265b13ee8f2adcd496da101ec99d4c9bd8e4f93c))
* set signed tag committer identity ([19b8e02](https://github.com/7K-Hiroba/workflows/commit/19b8e0295e9af1c37240ba9d053ea850c4b8554c))
* set signed tag committer identity ([36d2456](https://github.com/7K-Hiroba/workflows/commit/36d2456caee34e9ffc9711d8c8345671615626b0))
* share canonical template artifact key ([88f60a2](https://github.com/7K-Hiroba/workflows/commit/88f60a279b6676689e75388a080130d1902674f9))
* share canonical template artifact key ([41bf30a](https://github.com/7K-Hiroba/workflows/commit/41bf30aec45f303d951baa386761fb95511ecad9))
* use crane auth login for charts ([643374c](https://github.com/7K-Hiroba/workflows/commit/643374c7a84d7c8258cdc5b84706cac43b8be333))
* use crane auth login for charts ([4c28ec4](https://github.com/7K-Hiroba/workflows/commit/4c28ec460c4616743b88ba285ee6008168d7d35d))
* use default node cache behavior for extension UI ([2f66324](https://github.com/7K-Hiroba/workflows/commit/2f66324d640ab3240b9c3d68dece921848ab1b74))
* use default node cache behavior for extension UI ([fbb7d67](https://github.com/7K-Hiroba/workflows/commit/fbb7d67c98d02fec26dc5871533be7b664e99817))
* use exported source SHA in signed tag commands ([fa6a0d4](https://github.com/7K-Hiroba/workflows/commit/fa6a0d45b98ee46d741c1609cc0cd427c0f41a32))
* use exported source SHA in signed tag commands ([6866c4f](https://github.com/7K-Hiroba/workflows/commit/6866c4f7e056702d1b81d71ddc7f7f96a7fbb747))
* use Go 1.27 for signed release ([f299884](https://github.com/7K-Hiroba/workflows/commit/f299884a0454fb7882ceb8a39903ffae4fd3979e))
* use Go 1.27 for signed release ([df6628a](https://github.com/7K-Hiroba/workflows/commit/df6628abc38e6f58733acedea2fe692c7d3af0e0))
* use tag-aware gitsign verification ([f572c5a](https://github.com/7K-Hiroba/workflows/commit/f572c5a244e27e4a77589f2730066749c7b51c6b))
* use tag-aware gitsign verification ([247dda7](https://github.com/7K-Hiroba/workflows/commit/247dda73c4f70c7d78ebbd797b4dc00617ac1381))
* validate only required check contexts ([8d5179e](https://github.com/7K-Hiroba/workflows/commit/8d5179e8bdaeb001e602ac6c52c6d45369b80ec4))
* validate only required check contexts ([300afb0](https://github.com/7K-Hiroba/workflows/commit/300afb0bf30b67f1bd7a4789164bbd62f16b4ed1))
* verify chart content from OCI layout ([59817fa](https://github.com/7K-Hiroba/workflows/commit/59817faa57e5e0d7a8b1491669db96762145405c))
* verify chart content from OCI layout ([a0d2822](https://github.com/7K-Hiroba/workflows/commit/a0d28227c8ec432883b93029633284f389b809ef))
* verify concatenated cosign evidence streams ([#48](https://github.com/7K-Hiroba/workflows/issues/48)) ([43ae831](https://github.com/7K-Hiroba/workflows/commit/43ae83163c6bb58ef4d342dde9ec9c4bd8fdf53c))
* verify exact publisher ref identity ([67e851b](https://github.com/7K-Hiroba/workflows/commit/67e851b6c708703697ab309a88dabefcd1ffd059))
* verify library tags against exact ref ([a6410f8](https://github.com/7K-Hiroba/workflows/commit/a6410f83931c8787566883358c461c52e284cddb))
* verify library tags against exact ref ([9276d5e](https://github.com/7K-Hiroba/workflows/commit/9276d5e8db80fd909fd9a06125ded4fa805d9cc7))
* verify signed tags inside consumer repository ([1815e32](https://github.com/7K-Hiroba/workflows/commit/1815e3281c856ff3af9be83168d813518b411f23))
* verify signed tags inside consumer repository ([5696cf0](https://github.com/7K-Hiroba/workflows/commit/5696cf00f47d8a2f66945fb9ac4676b0463567b1))


### Documentation

* document app-config-v2 major migration ([#40](https://github.com/7K-Hiroba/workflows/issues/40)) ([90146fe](https://github.com/7K-Hiroba/workflows/commit/90146feb7f553ff51fa4d511c65f5602eaaaf0d4))

## [2.0.2](https://github.com/7K-Hiroba/workflows/compare/v2.0.0...v2.0.2) (2026-11-23)


### Recovery context

* Supersedes quarantined v2.0.0, which was published before required rehearsals, and unpublished/quarantined v2.0.1, whose standalone chart qualification failed. Both remain immutable and unadopted. No consumer adoption was authorized before the complete pre-release same-SHA rehearsal matrix and protected signing succeeded.
* The earlier #46 v2.0.2 candidate was invalidated when main advanced through the download-artifact v8 update (#6); it was not tagged and must not be reused. Release PR #47 replaced that candidate and included the update.
* v2.0.2 was never tagged and no GitHub Release was created; it is unpublished, quarantined, and unadopted. All five full rehearsals passed at `1ae0c537a525e9375d6d6d850eca7cc932c749e2`, and standalone chart run [45274871189](https://github.com/7K-Hiroba/workflows/actions/runs/45274871189) reproduced the exact scaffold chart digest `sha256:44170dc3b2f4afe267b2e03e948f7c54c72b22c04acce9ede3603ef281bccb99`, but evidence verification failed when Cosign returned concatenated full and standalone predicate documents. The next recovery version must be v2.0.3 at a new reviewed SHA after complete same-SHA qualification; v2.0.2 must not be reused.

### Bug Fixes

* make chart packaging reproducible ([#45](https://github.com/7K-Hiroba/workflows/issues/45)) ([3883213](https://github.com/7K-Hiroba/workflows/commit/388321348b6886c3e1675cfcb0190ffd5ee49c40))
* consume aggregated chart stack evidence ([#43](https://github.com/7K-Hiroba/workflows/issues/43)) ([ee2ec5a](https://github.com/7K-Hiroba/workflows/commit/ee2ec5ab5724b8e24f6eb65d9e43f1658f20a087))

### Dependency Updates

* update actions/download-artifact action to v8 ([#6](https://github.com/7K-Hiroba/workflows/issues/6)) ([b1d1e41](https://github.com/7K-Hiroba/workflows/commit/b1d1e417cd15ccfe2cf2b93b41b13d4111c248b0))

## [2.0.1](https://github.com/7K-Hiroba/workflows/compare/v2.0.0...v2.0.1) (2026-11-23)


### Recovery context

* Unpublished and unadopted. The standalone chart rehearsal exposed non-deterministic package bytes, so v2.0.1 was never tagged and must not be used. It is superseded by v2.0.2.

### Bug Fixes

* consume aggregated chart stack evidence ([#43](https://github.com/7K-Hiroba/workflows/issues/43)) ([ee2ec5a](https://github.com/7K-Hiroba/workflows/commit/ee2ec5ab5724b8e24f6eb65d9e43f1658f20a087))

## [2.0.0](https://github.com/7K-Hiroba/workflows/compare/v1.1.0...v2.0.0) (2026-11-23)


### ⚠ BREAKING CHANGES

* consumers adopting workflows v2.0.0 must migrate to inari.hiroba.app.v2 and explicitly select archetype stack or non-stack. Stacks must declare and pass install plus same-cluster upgrade lifecycle coverage; consumers not yet migrating must retain their immutable v1.1.0 pin.

### Features

* standardize classified stack testing ([#39](https://github.com/7K-Hiroba/workflows/issues/39)) ([7e61f10](https://github.com/7K-Hiroba/workflows/commit/7e61f10f1f78ebf9470a6f9343dd86d71e4e6447))
* support full-matrix release identities ([#37](https://github.com/7K-Hiroba/workflows/issues/37)) ([0c491e8](https://github.com/7K-Hiroba/workflows/commit/0c491e8811bc2b9688f8bb2a3eb6079fad955506))
* support Mimir observability assets ([#38](https://github.com/7K-Hiroba/workflows/issues/38)) ([ba015f6](https://github.com/7K-Hiroba/workflows/commit/ba015f62e5b5ab4cfccd01e5468bbfb26a9ac2ae))


### Bug Fixes

* normalize setup-node cache paths ([#41](https://github.com/7K-Hiroba/workflows/issues/41)) ([4208216](https://github.com/7K-Hiroba/workflows/commit/420821655637244e1b14826de2188e4d657c5fb5))


### Documentation

* document app-config-v2 major migration ([#40](https://github.com/7K-Hiroba/workflows/issues/40)) ([90146fe](https://github.com/7K-Hiroba/workflows/commit/90146feb7f553ff51fa4d511c65f5602eaaaf0d4))

## [1.1.0](https://github.com/7K-Hiroba/workflows/compare/v1.0.0...v1.1.0) (2026-11-20)


### Features

* add v2 observability producer contract ([#31](https://github.com/7K-Hiroba/workflows/issues/31)) ([7ecf629](https://github.com/7K-Hiroba/workflows/commit/7ecf629dd02c9acca82878c6487a3560025e0411))
* support full-matrix Hiroba scaffolds ([3406716](https://github.com/7K-Hiroba/workflows/commit/340671634ca6ea56fbeca54bacd7e18f5135c49b))


### Bug Fixes

* create GitHub release inside consumer repository ([8f9bb9f](https://github.com/7K-Hiroba/workflows/commit/8f9bb9f4b42b4a7a6a7ab327e38c9a0a8cc21c22))
* create GitHub release inside consumer repository ([0813e95](https://github.com/7K-Hiroba/workflows/commit/0813e9542c6347e174019d7f406c75b06038c220))
* create release evidence directory before runtime copy ([7bc0b00](https://github.com/7K-Hiroba/workflows/commit/7bc0b003994714c5e85f75bbd1afc1db969461c8))
* default fixture runtime evidence to ineligible ([#35](https://github.com/7K-Hiroba/workflows/issues/35)) ([f92f591](https://github.com/7K-Hiroba/workflows/commit/f92f591ca6eb515b46b3b6d284b739a5011aff99))
* grant artifact metadata writes to attestation jobs ([#32](https://github.com/7K-Hiroba/workflows/issues/32)) ([e9f81b3](https://github.com/7K-Hiroba/workflows/commit/e9f81b3d9250cc67f7e0c69772eb1a3840b8c0db))
* publish chartless rehearsal package chain ([#33](https://github.com/7K-Hiroba/workflows/issues/33)) ([c3bdc1e](https://github.com/7K-Hiroba/workflows/commit/c3bdc1e715391a8c66d599ce32356e6ea071e169))
* separate non-plugin package release identity ([#34](https://github.com/7K-Hiroba/workflows/issues/34)) ([265b13e](https://github.com/7K-Hiroba/workflows/commit/265b13ee8f2adcd496da101ec99d4c9bd8e4f93c))

## [1.0.0](https://github.com/7K-Hiroba/workflows/releases/tag/v1.0.0) (2026-11-15)


### Features

* add workflows v1 and trusted publishing ([#1](https://github.com/7K-Hiroba/workflows/issues/1)) ([78b2e66](https://github.com/7K-Hiroba/workflows/commit/78b2e662bc414aa231cf640e9f17168adaa66b53))


### Bug Fixes

* allow optional Helm manifest media type ([26eb586](https://github.com/7K-Hiroba/workflows/commit/26eb58679a590c13f9bdc71156494f1f8765e585))
* allow optional Helm manifest media type ([39481a0](https://github.com/7K-Hiroba/workflows/commit/39481a08747c739efd3a8daa62c1c4adb78dfb78))
* assemble canonical template evidence filenames ([95aa59c](https://github.com/7K-Hiroba/workflows/commit/95aa59c67d94551bcab6dff963ce9339a7bfdabf))
* assemble canonical template evidence filenames ([de4360a](https://github.com/7K-Hiroba/workflows/commit/de4360affab03d9e9da84c23a604162186a35c61))
* authenticate chart crane reads ([bb4a1ca](https://github.com/7K-Hiroba/workflows/commit/bb4a1ca92e079af5bfa06f6acd739f19e49a9e57))
* complete release permission chain ([#4](https://github.com/7K-Hiroba/workflows/issues/4)) ([fa01f9a](https://github.com/7K-Hiroba/workflows/commit/fa01f9aa41f8536f876c91b4f9935c7041b7d624))
* grant full rehearsal nested contents write ([#3](https://github.com/7K-Hiroba/workflows/issues/3)) ([f07f695](https://github.com/7K-Hiroba/workflows/commit/f07f6959a5afc3528fe334b4f9484349f47e616e))
* preserve compatibility evidence layout ([a7300a7](https://github.com/7K-Hiroba/workflows/commit/a7300a7fa2e649813c19f7c12273ebbcffca1b4c))
* preserve compatibility evidence layout ([12a0ede](https://github.com/7K-Hiroba/workflows/commit/12a0edef25d6f8ddedf1c99161848b98f17f92df))
* provide token to release verification ([2d5adf6](https://github.com/7K-Hiroba/workflows/commit/2d5adf649707d3ba50b355f8666ec2c8396223a9))
* provide token to release verification ([14e0ec8](https://github.com/7K-Hiroba/workflows/commit/14e0ec8e6ec6af30a9ec7d92d4e2594c4e5b4fbc))
* push backend from OCI layout ([3385a71](https://github.com/7K-Hiroba/workflows/commit/3385a71c2e9a8d61c6b4ab37932145b828df8928))
* resolve rehearsal publish failures ([b33284d](https://github.com/7K-Hiroba/workflows/commit/b33284d36ff2b65bb05c288129fdfe8f62bed09a))
* share canonical template artifact key ([88f60a2](https://github.com/7K-Hiroba/workflows/commit/88f60a279b6676689e75388a080130d1902674f9))
* share canonical template artifact key ([41bf30a](https://github.com/7K-Hiroba/workflows/commit/41bf30aec45f303d951baa386761fb95511ecad9))
* use crane auth login for charts ([643374c](https://github.com/7K-Hiroba/workflows/commit/643374c7a84d7c8258cdc5b84706cac43b8be333))
* use crane auth login for charts ([4c28ec4](https://github.com/7K-Hiroba/workflows/commit/4c28ec460c4616743b88ba285ee6008168d7d35d))
* use default node cache behavior for extension UI ([2f66324](https://github.com/7K-Hiroba/workflows/commit/2f66324d640ab3240b9c3d68dece921848ab1b74))
* use default node cache behavior for extension UI ([fbb7d67](https://github.com/7K-Hiroba/workflows/commit/fbb7d67c98d02fec26dc5871533be7b664e99817))
* verify chart content from OCI layout ([59817fa](https://github.com/7K-Hiroba/workflows/commit/59817faa57e5e0d7a8b1491669db96762145405c))
* verify chart content from OCI layout ([a0d2822](https://github.com/7K-Hiroba/workflows/commit/a0d28227c8ec432883b93029633284f389b809ef))
* verify exact publisher ref identity ([67e851b](https://github.com/7K-Hiroba/workflows/commit/67e851b6c708703697ab309a88dabefcd1ffd059))
* verify library tags against exact ref ([a6410f8](https://github.com/7K-Hiroba/workflows/commit/a6410f83931c8787566883358c461c52e284cddb))
* verify library tags against exact ref ([9276d5e](https://github.com/7K-Hiroba/workflows/commit/9276d5e8db80fd909fd9a06125ded4fa805d9cc7))

## [0.1.0]

Initial development state. No immutable workflow release has been published.
