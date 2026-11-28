#include <cstdlib>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <thread>
#include <vector>

constexpr int W = 1000, CH = 998, H = 2166, OY = 584, LH = OY + CH;
static float T = 0, P = 8, LOOP0 = -1, ANGLE = 0, YAW = 0, PITCH = 0, FX = 0, FY = 0, FS = 1;
constexpr float F = 1100, HORIZON = 538;
constexpr float TOP = -2.9f, BOTTOM = -4.3f, DOWN = 640;

struct V {
    float x, y, z;
    V operator+(V b) const { return {x + b.x, y + b.y, z + b.z}; }
    V operator-(V b) const { return {x - b.x, y - b.y, z - b.z}; }
    V operator*(float s) const { return {x * s, y * s, z * s}; }
};
static V mix(V a, V b, float t) { return a + (b - a) * t; }
static float clamp01(float x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
static float smooth(float a, float b, float x) {
    float t = clamp01((x - a) / (b - a));
    return t * t * (3 - 2 * t);
}
static V rgb(float r, float g, float b) { return {r / 255, g / 255, b / 255}; }

constexpr int N = 128, M = 96;
static std::vector<float> lattice, cells;

static float tri(const std::vector<float>& t, int n, float x, float y, float z, bool ease) {
    float fx = std::floor(x), fy = std::floor(y), fz = std::floor(z);
    float u = x - fx, v = y - fy, w = z - fz;
    if (ease) {
        u = u * u * (3 - 2 * u);
        v = v * v * (3 - 2 * v);
        w = w * w * (3 - 2 * w);
    }
    int x0 = ((int)fx % n + n) % n, y0 = ((int)fy % n + n) % n, z0 = ((int)fz % n + n) % n;
    int x1 = (x0 + 1) % n, y1 = (y0 + 1) % n, z1 = (z0 + 1) % n;
    auto at = [&](int i, int j, int k) { return t[(k * n + j) * n + i]; };
    float a = at(x0, y0, z0) + (at(x1, y0, z0) - at(x0, y0, z0)) * u;
    float b = at(x0, y1, z0) + (at(x1, y1, z0) - at(x0, y1, z0)) * u;
    float c = at(x0, y0, z1) + (at(x1, y0, z1) - at(x0, y0, z1)) * u;
    float d = at(x0, y1, z1) + (at(x1, y1, z1) - at(x0, y1, z1)) * u;
    float e = a + (b - a) * v, g = c + (d - c) * v;
    return e + (g - e) * w;
}
static float noise(V p) { return tri(lattice, N, p.x, p.y, p.z, true); }
static float puff(V p) { return tri(cells, M, p.x * 12, p.y * 12, p.z * 12, false); }
static float fbm(V p, int octaves) {
    float sum = 0, amp = 0.5f, norm = 0;
    for (int i = 0; i < octaves; i++) {
        sum += amp * noise(p);
        norm += amp;
        amp *= 0.5f;
        p = p * 2.03f + V{7.1f, 3.7f, 5.3f};
    }
    return sum / norm;
}

static void build() {
    std::mt19937 gen(7);
    std::uniform_real_distribution<float> uni(0, 1);
    lattice.resize(N * N * N);
    for (auto& v : lattice) v = uni(gen);
    constexpr int C = 8;
    std::vector<V> points(C * C * C);
    for (auto& p : points) p = {uni(gen), uni(gen), uni(gen)};
    cells.resize(M * M * M);
    for (int k = 0; k < M; k++)
        for (int j = 0; j < M; j++)
            for (int i = 0; i < M; i++) {
                V p = {i * C / (float)M, j * C / (float)M, k * C / (float)M};
                float best = 9;
                for (int dz = -1; dz <= 1; dz++)
                    for (int dy = -1; dy <= 1; dy++)
                        for (int dx = -1; dx <= 1; dx++) {
                            int cx = (int)p.x + dx, cy = (int)p.y + dy, cz = (int)p.z + dz;
                            V q = points[(((cz + C) % C) * C + (cy + C) % C) * C + (cx + C) % C];
                            V d = V{cx + q.x, cy + q.y, cz + q.z} - p;
                            best = std::min(best, d.x * d.x + d.y * d.y + d.z * d.z);
                        }
                cells[(k * M + j) * M + i] = 1 - std::min(1.0f, std::sqrt(best));
            }
}

static float density(V p, float far, bool fine) {
    float h = (p.y - BOTTOM) / (TOP - BOTTOM);
    if (h <= 0 || h >= 1) return 0;
    p = p + V{noise(p * 2.1f) - 0.5f, (noise(p * 2.4f + V{5.2f, 1.3f, 8.8f}) - 0.5f) * 0.4f, noise(p * 2.2f + V{9.1f, 4.4f, 2.6f}) - 0.5f} * 0.34f;
    float cover = fbm({p.x * 0.80f + 11.3f, 0.5f, p.z * 0.72f + 2.9f}, 4);
    cover += (noise({p.x * 0.27f + 3.0f, 7.5f, p.z * 0.27f}) - 0.5f) * 0.24f;
    float billow = 0.55f * puff(p * 1.35f) + 0.30f * puff(p * 3.0f + V{0.3f, 0.1f, 0.7f}) + 0.15f * puff(p * 6.4f);
    float d = (cover - 0.462f) * 3.1f + (billow - 0.48f) * 1.7f - std::max(0.0f, h - 0.30f) * 1.25f;
    if (d <= -0.12f) return 0;
    if (fine && far < 40) d -= (0.62f - fbm(p * 7.5f, 4)) * 1.15f * (1 - smooth(18, 55, far));
    return clamp01(d * 2.2f) * smooth(0.0f, 0.18f, h);
}

static const float ROWS[] = {0,30,60,90,120,150,180,210,240,270,300,330,360,385,405,425,445,465,485,505,520,535,560};
static const float COLUMNS[] = {15,80,160,240,320,365,600,670,750,840,920,985};
static const float SKY[12][23][3] = {{{56,65,79},{53,64,81},{54,68,86},{56,70,97},{58,73,104},{59,73,109},{60,78,122},{61,87,137},{65,95,150},{61,98,161},{64,103,171},{64,108,179},{67,117,185},{69,123,193},{73,131,196},{77,137,197},{86,146,199},{99,156,200},{110,164,199},{109,161,195},{103,154,191},{98,143,184},{148,166,183}},{{54,66,83},{53,67,85},{55,71,95},{56,72,101},{59,75,108},{59,77,119},{61,84,131},{62,89,144},{62,93,150},{60,99,160},{63,104,170},{63,111,179},{66,117,184},{69,126,192},{73,134,193},{79,142,193},{90,154,195},{102,163,196},{118,172,198},{122,171,193},{117,164,189},{108,156,184},{163,175,182}},{{59,73,89},{58,74,95},{57,72,97},{57,73,104},{60,75,112},{60,79,122},{56,83,132},{59,89,142},{61,94,155},{59,100,162},{60,106,169},{64,114,179},{64,119,186},{71,131,189},{77,140,194},{86,150,193},{103,165,199},{118,174,197},{129,180,194},{137,182,191},{134,179,189},{131,172,185},{186,191,184}},{{55,70,89},{54,71,94},{58,73,104},{56,72,104},{57,76,116},{57,79,127},{59,87,138},{58,89,146},{59,97,158},{60,102,165},{60,109,176},{64,116,182},{67,124,188},{75,137,192},{81,146,194},{91,158,198},{109,172,201},{129,183,201},{140,186,195},{151,190,193},{147,186,190},{146,183,186},{188,194,178}},{{57,73,97},{57,73,99},{59,75,106},{58,77,113},{61,84,123},{60,85,134},{62,88,143},{60,93,149},{57,96,159},{59,102,165},{60,109,173},{63,115,181},{66,123,186},{74,138,191},{82,146,194},{97,162,198},{111,176,200},{135,186,202},{149,192,198},{158,194,193},{156,192,191},{155,188,185},{204,203,177}},{{60,77,103},{60,78,109},{60,78,110},{61,78,114},{61,81,124},{60,85,133},{59,89,139},{60,92,149},{57,95,155},{61,102,165},{60,109,175},{62,115,180},{68,123,186},{75,138,190},{83,147,192},{97,162,196},{115,176,200},{137,187,201},{149,192,195},{159,195,192},{156,192,190},{160,190,184},{207,202,175}},{{60,86,119},{58,90,130},{62,93,134},{59,93,136},{59,93,138},{60,88,137},{59,90,145},{60,94,152},{60,97,161},{60,104,171},{59,110,176},{64,118,182},{67,127,189},{75,142,193},{87,153,198},{103,167,201},{119,179,201},{139,189,198},{153,195,196},{162,195,190},{161,177,166},{165,188,180},{203,184,155}},{{64,84,115},{59,84,120},{59,86,126},{60,89,129},{60,90,134},{61,90,138},{60,92,148},{61,95,151},{59,99,161},{60,108,168},{61,112,177},{65,117,180},{66,127,188},{76,141,192},{86,152,197},{99,165,198},{119,178,200},{138,187,199},{151,194,198},{161,196,193},{158,194,190},{165,190,187},{211,204,179}},{{59,81,111},{57,81,115},{58,84,124},{59,87,127},{60,88,129},{60,90,140},{60,92,149},{60,96,153},{60,98,162},{60,105,171},{62,112,176},{62,119,185},{69,131,192},{75,140,194},{88,153,197},{102,168,199},{120,178,202},{138,189,201},{150,194,199},{159,195,198},{156,192,191},{158,188,191},{207,202,180}},{{61,80,108},{59,80,110},{57,81,116},{57,84,120},{56,83,126},{58,88,135},{58,89,142},{60,95,151},{58,97,159},{61,104,166},{59,109,177},{62,115,182},{68,128,193},{75,139,198},{86,151,200},{101,165,202},{113,176,206},{132,184,205},{144,190,200},{149,190,198},{144,185,196},{145,182,192},{202,200,184}},{{58,80,106},{60,81,110},{59,83,118},{61,88,127},{62,90,131},{62,91,135},{61,94,144},{61,96,151},{61,99,158},{63,103,166},{60,108,175},{62,115,183},{65,122,191},{73,133,194},{80,145,198},{91,154,199},{106,167,204},{117,177,203},{131,181,200},{133,181,200},{130,175,198},{126,168,192},{188,192,193}},{{60,76,100},{59,79,106},{60,81,114},{59,85,120},{60,89,129},{63,91,135},{61,92,141},{63,97,150},{62,99,159},{63,107,170},{61,107,175},{65,115,184},{66,119,191},{72,129,198},{79,140,202},{89,150,203},{99,161,205},{106,167,205},{118,173,203},{120,169,199},{114,162,195},{112,155,192},{171,182,192}}};

static V sky(float u, float v) {
    int i = 0;
    while (i < 21 && v > ROWS[i + 1]) i++;
    float t = clamp01((v - ROWS[i]) / (ROWS[i + 1] - ROWS[i]));
    int j = 0;
    while (j < 10 && u > COLUMNS[j + 1]) j++;
    float s = clamp01((u - COLUMNS[j]) / (COLUMNS[j + 1] - COLUMNS[j]));
    auto col = [&](int k) { return mix(rgb(SKY[k][i][0], SKY[k][i][1], SKY[k][i][2]), rgb(SKY[k][i + 1][0], SKY[k][i + 1][1], SKY[k][i + 1][2]), t); };
    V c = mix(col(j), col(j + 1), s);
    float mottled = fbm({u / 90, v / 55, 3.3f}, 5) - 0.5f;
    float up = clamp01(-v / OY);
    c = mix(c, rgb(14, 22, 48), up * 0.75f);
    return c * (1 + mottled * 0.16f * (1 - smooth(80, 380, v)));
}

static V palette(float x) {
    static const float at[] = {0.0f, 0.25f, 0.45f, 0.62f, 0.78f, 0.9f, 1.0f};
    static const V c[] = {rgb(70, 96, 142), rgb(96, 118, 162), rgb(144, 156, 188), rgb(194, 192, 196), rgb(222, 210, 193), rgb(234, 221, 195), rgb(244, 231, 204)};
    int i = 0;
    while (i < 5 && x > at[i + 1]) i++;
    return mix(c[i], c[i + 1], clamp01((x - at[i]) / (at[i + 1] - at[i])));
}

static V clouds(float u, float v, float jitter) {
    float below = v - HORIZON;
    if (below > 0) below += 46 * (1 - std::exp(-below / 22));
    V d = {(u - W / 2) / F, -below / DOWN, 1};
    float len = std::sqrt(d.x * d.x + d.y * d.y + 1);
    d = d * (1 / len);
    V back = sky(u, v);
    if (d.y > -0.0012f) return back;
    float t0 = TOP / d.y, t1 = BOTTOM / d.y;
    V sun = {-0.62f, 0.66f, -0.42f};
    float T = 1, light = 0, dist = 0;
    float t = t0 + jitter * std::max(0.025f, t0 * 0.005f);
    for (int i = 0; i < 360 && t < t1 && t < 220 && T > 0.015f; i++) {
        float dt = std::max(0.025f, t * 0.005f);
        V p = d * t;
        float rho = density(p, t, true);
        if (rho > 0.001f) {
            float tau = 0, last = 0;
            for (float s : {0.05f, 0.12f, 0.24f, 0.45f, 0.8f, 1.3f}) {
                tau += density(p + sun * s, t, false) * (s - last);
                last = s;
            }
            float h = (p.y - BOTTOM) / (TOP - BOTTOM);
            float lit = 0.80f * std::exp(-tau * 3.4f) + 0.42f * smooth(0.1f, 0.85f, h);
            float a = 1 - std::exp(-rho * 5.6f * dt);
            light += T * a * lit;
            dist += T * a * t;
            T *= 1 - a;
        }
        t += dt;
    }
    float alpha = 1 - T;
    float ground = (BOTTOM - 0.5f) / d.y;
    V g = d * ground;
    float patch = fbm({g.x * 1.7f + fbm({g.x * 2.3f, 1.0f, g.z * 1.1f}, 3), 9.1f, g.z * 0.9f}, 6);
    V under = mix(rgb(66, 98, 144), rgb(104, 138, 176), smooth(0.36f, 0.72f, patch));
    V col = under;
    float zone = fbm({g.x * 0.33f + 4.0f, 2.2f, g.z * 0.33f}, 3);
    float shade = 1 - (1 - smooth(6, 30, t0)) * (0.0f + 0.30f * smooth(0.58f, 0.38f, zone));
    if (alpha > 0.001f) col = mix(under, palette(clamp01(light / alpha * shade)), smooth(0.0f, 0.92f, alpha));
    float reach = alpha > 0.4f ? dist / alpha : t0 * 1.15f;
    float fog = 1 - std::exp(-std::max(0.0f, reach - 10) / 80);
    V haze = mix(rgb(224, 214, 186), rgb(176, 192, 194), smooth(45, 150, reach));
    col = mix(col, haze, fog);
    return mix(back, col, smooth(HORIZON + 1, HORIZON + 17, v));
}

static const float FLAME[][2] = {{401, 280}, {405, 282.5f}, {405, 289}, {404.5f, 300}, {405, 309}, {413, 309}, {420, 310.5f}, {427, 316}, {429.5f, 324}, {431.5f, 332}, {434, 339}, {440, 344}, {445, 348}, {447, 356}, {445, 363}, {440, 366}, {434, 368}, {425, 369}, {418, 368.5f}, {414, 367}, {410, 364}, {409.5f, 356}, {407, 350}, {399, 346}, {394.5f, 342}, {393, 335}, {393.5f, 326}, {389, 322}, {389.5f, 316}, {392.5f, 308}, {391, 298}, {388.5f, 295}, {391, 289}, {395, 284}};
static const float TONES[][5] = {{397,282,188,139,109},{393,291,248,182,91},{399,288,188,144,83},{394,300,226,164,95},{398,307,241,165,88},{391,318,217,180,111},{397,318,210,128,59},{396,328,218,166,96},{399,338,174,131,88},{405,305,197,112,71},{412,314,199,116,75},{421,318,208,122,77},{408,322,220,141,75},{417,327,201,97,61},{425,330,230,127,55},{402,332,212,129,65},{411,334,238,177,73},{423,337,232,168,64},{415,341,239,182,69},{405,345,174,116,76},{414,348,237,187,72},{424,347,246,157,68},{432,343,226,139,72},{413,355,236,170,78},{421,357,201,106,47},{431,352,216,121,60},{441,353,202,134,77},{412,363,217,167,115},{422,364,204,125,88},{433,362,169,106,56},{442,361,221,140,86},{400,297,195,143,80},{409,301,72,51,41},{429,358,162,81,49},{419,334,237,177,70},{403,316,129,89,53}};

static float outline(float x, float y) {
    constexpr int n = sizeof(FLAME) / sizeof(FLAME[0]);
    float best = 1e9f;
    bool inside = false;
    for (int i = 0, j = n - 1; i < n; j = i++) {
        float ax = FLAME[j][0], ay = FLAME[j][1], bx = FLAME[i][0], by = FLAME[i][1];
        float ex = bx - ax, ey = by - ay;
        float t = clamp01(((x - ax) * ex + (y - ay) * ey) / (ex * ex + ey * ey));
        float dx = x - ax - ex * t, dy = y - ay - ey * t;
        best = std::min(best, dx * dx + dy * dy);
        if ((by > y) != (ay > y) && x < (ax - bx) * (y - by) / (ay - by) + bx) inside = !inside;
    }
    return (inside ? 1 : -1) * std::sqrt(best);
}

static V burn(V& under, float x, float y) {
    if (x < 370 || x > 470 || y < 250 || y > 390) return {0, 0, 0};
    float rise = T * 55.0f;
    float wx = fbm({x / 8.0f, (y + rise) / 12.0f, 2.2f + T * 2.6f}, 4) - 0.5f, wy = fbm({x / 8.0f, (y + rise) / 12.0f, 9.4f + T * 2.6f}, 4) - 0.5f;
    float px = x + wx * 12, py = y + wy * 15;
    float lick = fbm({px / 4.2f, (py + rise * 1.6f) / 7.0f, 4.1f + T * 3.4f}, 4) - 0.5f;
    float d = outline(px, py);
    float a = smooth(-3.0f, 3.5f, d + lick * 9) * (0.96f - 0.34f * smooth(355, 369, y));
    V sum = {0, 0, 0};
    float total = 1e-6f;
    for (auto& t : TONES) {
        float dx = px - t[0], dy = py - t[1];
        float w = std::exp(-(dx * dx + dy * dy) / 20.0f) + 1e-5f / (1 + dx * dx + dy * dy);
        sum = sum + rgb(t[2], t[3], t[4]) * w;
        total += w;
    }
    V col = sum * (1 / total);
    float grain = fbm({px / 3.0f, (py + rise) / 4.6f, 6.6f + T * 3.0f}, 4) - 0.5f;
    col = col + V{0.62f, 0.50f, 0.18f} * (grain * 0.75f);
    auto spot = [&](float cx, float cy, float rx, float ry) {
        float ex = (px - cx) / rx, ey = (py - cy) / ry;
        return std::exp(-(ex * ex + ey * ey));
    };
    float fleck = spot(405, 312.5f, 3.2f, 2.6f) + spot(409.5f, 317, 2.0f, 2.6f) + 0.8f * spot(418, 322, 1.6f, 4.0f) + 0.7f * spot(403, 327, 1.5f, 2.0f);
    col = mix(col, rgb(62, 30, 20), clamp01(fleck));
    float mid = col.x * 0.3f + col.y * 0.6f + col.z * 0.1f;
    col = V{mid, mid, mid} + (col - V{mid, mid, mid}) * 1.2f;
    col = (col - V{0.52f, 0.40f, 0.28f}) * 1.12f + V{0.535f, 0.405f, 0.27f};
    col = {clamp01(col.x), clamp01(col.y), clamp01(col.z)};
    float ember = std::exp(-std::pow((px - (0.31f * (py - 368) + 428)) / 7.0f, 2.0f)) * smooth(356, 366, py) * (1 - smooth(372, 394, py));
    under = mix(under, rgb(150, 74, 46), ember * 0.62f * smooth(0.35f, 0.65f, fbm({px / 3.0f, py / 6.0f, 7.7f}, 4)) * (under.z < under.x ? 1.0f : 0.0f));
    under = mix(under, col, a);
    float wisp = spot(399, 272, 6, 8) * smooth(0.45f, 0.75f, fbm({px / 3.0f, py / 3.5f, 1.3f}, 4)) * 0.55f;
    under = mix(under, rgb(170, 130, 120), wisp);
    float spark = clamp01(spot(440.5f, 331, 1.3f, 3.2f) * 0.85f + spot(439, 326, 1.0f, 1.6f) * 0.6f);
    under = mix(under, rgb(206, 190, 160), spark);
    return col * (a * smooth(0.55f, 0.95f, col.x * 0.5f + col.y * 0.5f) * 0.6f);
}

int main(int argc, char** argv) {
    if (argc < 5) return 1;
    T = std::atof(argv[3]);
    int seed = std::atoi(argv[4]);
    if (argc > 5) LOOP0 = std::atof(argv[5]);
    if (argc > 6) ANGLE = std::atof(argv[6]);
    if (argc > 7) YAW = std::atof(argv[7]);
    if (argc > 8) PITCH = std::atof(argv[8]);
    if (argc > 10) {
        FX = std::atof(argv[9]);
        FY = std::atof(argv[10]);
    }
    if (argc > 11) FS = std::atof(argv[11]);
    build();
    std::vector<V> img(W * H);
    FILE* cache = std::fopen("tall.cache", "rb");
    bool cached = cache && std::fread(img.data(), sizeof(V), img.size(), cache) == img.size();
    if (cache) std::fclose(cache);
    std::atomic<int> next{cached ? H : 0};
    std::vector<std::thread> pool;
    for (unsigned n = 0; n < std::thread::hardware_concurrency(); n++)
        pool.emplace_back([&] {
            for (int y; (y = next++) < H;)
                for (int x = 0; x < W; x++) {
                    V sum = {0, 0, 0};
                    int s = y - OY > HORIZON - 2 ? 2 : 1;
                    for (int j = 0; j < s; j++)
                        for (int i = 0; i < s; i++) {
                            float jitter = std::fmod(52.9829189f * std::fmod(0.06711056f * (x * s + i) + 0.00583715f * (y * s + j), 1.0f), 1.0f);
                            sum = sum + clouds(x + (i + 0.5f) / s, y - OY + (j + 0.5f) / s, jitter);
                        }
                    img[y * W + x] = sum * (1.0f / (s * s));
                }
        });
    for (auto& th : pool) th.join();
    if (!cached) {
        cache = std::fopen("tall.cache", "wb");
        std::fwrite(img.data(), sizeof(V), img.size(), cache);
        std::fclose(cache);
    }

    {
        std::vector<unsigned char> raw(W * CH * 3);
        FILE* f = std::fopen("ref.rgb", "rb");
        if (!f || std::fread(raw.data(), 1, raw.size(), f) != raw.size()) return 1;
        std::fclose(f);
        auto luma = [](V c) { return c.x * 0.3f + c.y * 0.6f + c.z * 0.1f; };
        const int centre[] = {552, 575, 610, 660, 740, 840, 945}, half[] = {9, 15, 22, 32, 48, 55, 53};
        constexpr int bands = 7, bins = 128;
        std::vector<float> mine[bands];
        std::vector<V> theirs[bands];
        for (int b = 0; b < bands; b++) {
            std::vector<std::pair<float, V>> ref;
            for (int y = centre[b] - half[b]; y < std::min(CH, centre[b] + half[b]); y++)
                for (int x = 0; x < W; x++) {
                    if ((x > 370 && x < 690 && y < 750) || (x > 875 && y > 905)) continue;
                    const unsigned char* p = &raw[(y * W + x) * 3];
                    V c = rgb(p[0], p[1], p[2]);
                    ref.push_back({luma(c), c});
                    mine[b].push_back(luma(img[(y + OY) * W + x]));
                }
            std::sort(ref.begin(), ref.end(), [](auto& a, auto& c) { return a.first < c.first; });
            std::sort(mine[b].begin(), mine[b].end());
            for (int k = 0; k < bins; k++) {
                size_t from = ref.size() * k / bins, to = ref.size() * (k + 1) / bins;
                V sum = {0, 0, 0};
                for (size_t n = from; n < to; n++) sum = sum + ref[n].second;
                theirs[b].push_back(sum * (1.0f / (to - from)));
            }
        }
        for (int y = HORIZON + 1; y < H - OY; y++) {
            int b = 0;
            while (b < bands - 2 && y > centre[b + 1]) b++;
            float t = clamp01((y - centre[b]) / float(centre[b + 1] - centre[b]));
            for (int x = 0; x < W; x++) {
                V& c = img[(y + OY) * W + x];
                float l = luma(c);
                auto look = [&](int k) {
                    float p = (std::lower_bound(mine[k].begin(), mine[k].end(), l) - mine[k].begin()) / float(mine[k].size()) * bins - 0.5f;
                    int n = std::max(0, std::min(bins - 2, (int)p));
                    return mix(theirs[k][n], theirs[k][n + 1], clamp01(p - n));
                };
                c = mix(c, mix(look(b), look(b + 1), t), smooth(HORIZON + 1, HORIZON + 16, y));
            }
        }
    }
    {
        std::vector<V> still = img;
        float w = 6.2831853f / P;
        for (int y = (int)HORIZON + 2; y < CH; y++) {
            float depth = smooth(HORIZON, CH, y);
            float reach = 30.0f + 110.0f * depth;
            for (int x = 0; x < W; x++) {
                float hold = 1;
                auto at = [&](int a, int b) { return still[(b + OY) * W + a]; };
                V sum = {0, 0, 0};
                for (int k = 0; k < 2; k++) {
                    float cyc = std::fmod(T / P + 0.5f * k + 100.0f, 1.0f);
                    float weight = 1 - std::fabs(2 * cyc - 1);
                    float dx = reach * hold * (cyc - 0.5f);
                    float sx = std::min(W - 1.001f, std::max(0.0f, x + dx));
                    int ix = (int)sx;
                    float fx = sx - ix;
                    sum = sum + mix(at(ix, y), at(ix + 1, y), fx) * weight;
                }
                img[(y + OY) * W + x] = sum;
            }
        }
    }
    std::mt19937 gen(21);
    std::uniform_real_distribution<float> uni(0, 1);
    std::normal_distribution<float> spread(0, 1);
    auto star = [&](float sx, float sy0, float bright, float radius, V tint) {
        float sy = sy0 + OY;
        float h = std::fmod(std::fabs(std::sin(sx * 12.9898f + sy0 * 78.233f) * 43758.5453f), 1.0f), h2 = std::fmod(h * 7.31f, 1.0f);
        bright *= 1 + (0.15f + 0.35f * h2) * std::sin(6.2831853f * (T / P * 2 * (1 + int(h * 3)) + h2));
        for (int y = std::max(0, (int)sy - 3); y < std::min(H, (int)sy + 4); y++)
            for (int x = std::max(0, (int)sx - 3); x < std::min(W, (int)sx + 4); x++) {
                float cover = 0;
                for (int j = 0; j < 5; j++)
                    for (int i = 0; i < 5; i++) {
                        float dx = x + (i + 0.5f) / 5 - sx, dy = y + (j + 0.5f) / 5 - sy;
                        cover += std::exp(-(dx * dx + dy * dy) / (radius * radius));
                    }
                V& c = img[y * W + x];
                c = mix(c, tint, clamp01(bright * 1.08f * cover / 25));
            }
    };
    FILE* list = std::fopen("stars.txt", "r");
    if (!list) return 1;
    float sx, sy, peak, size;
    while (std::fscanf(list, "%f %f %f %f", &sx, &sy, &peak, &size) == 4) {
        float radius = 0.80f + 0.09f * std::sqrt(size);
        star(sx, sy, clamp01(0.12f + peak * 3.8f), radius, mix(rgb(214, 230, 255), rgb(255, 238, 205), uni(gen)));
        if (sy < 470) star(W - sx, -sy * 1.24f - 8, clamp01(0.12f + peak * 3.8f) * 0.9f, radius, mix(rgb(214, 230, 255), rgb(255, 238, 205), uni(gen)));
    }
    std::fclose(list);
    for (int i = 0; i < 5200; i++) {
        float x = uni(gen) * W, y = -OY + uni(gen) * OY;
        star(x, y, (0.12f + 0.40f * std::pow(uni(gen), 3.0f)) * (0.55f + 0.45f * clamp01(-y / OY)), 0.55f + 0.3f * std::pow(uni(gen), 5.0f), mix(rgb(205, 222, 250), rgb(255, 240, 215), uni(gen)));
    }
    for (int i = 0; i < 4200; i++) {
        float x = uni(gen) * W, y = uni(gen) * 480;
        float bright = (0.15f + 0.38f * std::pow(uni(gen), 3.0f)) * (1 - smooth(330, 480, y));
        star(x, y, bright, 0.55f, rgb(205, 222, 250));
    }
    for (int i = 0; i < 330; i++) {
        float x = 580 + uni(gen) * 420, y = 240 + uni(gen) * 225;
        float bright = (0.22f + 0.55f * std::pow(uni(gen), 2.5f)) * (1 - 0.5f * smooth(400, 470, y));
        star(x, y, bright, 0.62f + 0.4f * std::pow(uni(gen), 4.0f), mix(rgb(200, 232, 255), rgb(240, 245, 225), uni(gen)));
    }
    star(772, 449, 0.95f, 1.5f, rgb(225, 245, 255));
    star(773, 413, 0.85f, 1.25f, rgb(255, 244, 215));
    star(862, 436, 0.6f, 1.0f, rgb(220, 240, 255));
    for (int i = 0; i < 380; i++) {
        float x = uni(gen) * W, y = 170 + uni(gen) * 285;
        float bright = (0.30f + 0.55f * std::pow(uni(gen), 3.0f)) * (1 - 0.6f * smooth(380, 460, y));
        star(x, y, bright, 0.62f + 0.35f * std::pow(uni(gen), 4.0f), mix(rgb(220, 235, 255), rgb(255, 238, 205), uni(gen)));
    }
    for (int i = 0; i < 4200; i++) {
        float along = spread(gen), across = spread(gen);
        float x = 520 + along * 105 - across * 18, y = 30 + along * 42 + across * 34;
        if (x < 0 || x >= W || y < -OY || y >= CH) continue;
        star(x, y, 0.16f + 0.42f * std::pow(uni(gen), 3.0f), 0.62f, rgb(150, 200, 244));
    }

    {
        const float spots[7][3] = {{150, -430, 0.10f}, {830, -330, -0.15f}, {300, -150, 0.05f}, {905, 20, 0.2f}, {95, 160, -0.1f}, {640, -490, 0.12f}, {520, -220, -0.05f}};
        for (int g = 0; g < 7; g++) {
            float cx = spots[g][0], cy = spots[g][1], turn = spots[g][2], size = 20;
            float fade = smooth(0.3f, 0.85f, 0.5f + 0.5f * std::sin(6.2831853f * (T / P + g / 7.0f)));
            auto dot = [&](float u, float v) {
                float c = std::cos(turn), s = std::sin(turn);
                star(cx + (u * c - v * s) * size, cy + (u * s + v * c) * size, 0.95f * fade, 1.15f, mix(rgb(214, 230, 255), rgb(255, 238, 205), 0.4f));
            };
            auto arc = [&](float ox, float oy, float r, float a0, float a1) {
                int n = std::max(2, (int)(std::fabs(a1 - a0) * r * size / 6.5f));
                for (int i = 0; i <= n; i++) {
                    float a = a0 + (a1 - a0) * i / n;
                    dot(ox + r * std::cos(a), oy + r * std::sin(a));
                }
            };
            auto line = [&](float x0, float y0, float x1, float y1) {
                int n = std::max(1, (int)(std::hypot(x1 - x0, y1 - y0) * size / 6.5f));
                for (int i = 0; i <= n; i++) dot(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n);
            };
            const float pi = 3.14159265f;
            if (g == 0) { arc(0, 0, 1, 0, 2 * pi); dot(0, 0); }
            if (g == 1) { arc(0, 0, 1, pi * 0.5f, pi * 1.5f); arc(-0.55f, 0, 0.85f, pi * 0.62f, pi * 1.38f); }
            if (g == 2) { arc(0, -0.2f, 0.6f, 0, 2 * pi); arc(0, -1.15f, 0.45f, pi * 0.15f, pi * 0.85f); line(0, 0.4f, 0, 1.4f); line(-0.4f, 0.95f, 0.4f, 0.95f); }
            if (g == 3) { arc(0, -0.45f, 0.7f, 0, 2 * pi); line(0, 0.25f, 0, 1.4f); line(-0.45f, 0.85f, 0.45f, 0.85f); }
            if (g == 4) { arc(-0.25f, 0.25f, 0.7f, 0, 2 * pi); line(0.25f, -0.25f, 0.95f, -0.95f); line(0.95f, -0.95f, 0.35f, -0.95f); line(0.95f, -0.95f, 0.95f, -0.35f); }
            if (g == 5) { arc(-0.45f, -0.55f, 0.5f, pi * 1.1f, pi * 2.35f); line(-0.1f, -0.1f, -0.75f, 0.45f); line(-0.75f, 0.45f, 0.8f, 0.45f); line(0.45f, -0.9f, 0.45f, 1.1f); }
            if (g == 6) { line(-0.3f, -1.1f, -0.3f, 0.6f); line(-0.75f, -0.7f, 0.15f, -0.7f); arc(0.15f, 0.1f, 0.45f, pi * 1.0f, pi * 2.2f); arc(0.75f, 0.85f, 0.4f, pi * 1.2f, pi * 0.6f); }
        }
    }
    std::vector<V> bare = img;
    std::vector<float> held(W * CH, 0.0f);
    if (argc > 2) {
        FILE* in = std::fopen(argv[2], "rb");
        if (!in) return 1;
        std::vector<unsigned char> a(W * LH * 4);
        if (std::fread(a.data(), 1, a.size(), in) != a.size()) return 1;
        std::fclose(in);
        std::vector<V> glow(W * LH, {0, 0, 0});
        {
            std::vector<unsigned char> soft = a;
            for (int y = 1; y < LH - 1; y++)
                for (int x = 1; x < W - 1; x++)
                    for (int k = 0; k < 4; k++) {
                        int i = (y * W + x) * 4 + k;
                        soft[i] = (unsigned char)((8 * a[i] + a[i - 4] + a[i + 4] + a[i - W * 4] + a[i + W * 4] + 6) / 12);
                    }
            a.swap(soft);
        }
        for (int y = -OY; y < CH; y++)
            for (int x = 0; x < W; x++) {
                const unsigned char* p = &a[((y + OY) * W + x) * 4];
                V& here = img[(y + OY) * W + x];
                V c = rgb(p[0], p[1], p[2]);
                float wisp = fbm({x / 34.0f, y / 20.0f, 1.7f}, 5) - 0.5f;
                float cover = p[3] / 255.0f * (1 - smooth(700, 738, y + wisp * 60));
                c = V{0.105f, 0.080f, 0.072f} + V{c.x * 0.905f, std::pow(c.y, 0.93f) * 0.915f, c.z * 0.865f};
                here = mix(here, c, cover);
                if (y >= 0) held[y * W + x] = cover;
                float swirl = fbm({x / 22.0f, y / 15.0f, 8.2f}, 5);
                float ex = (x - 590) / 105.0f, ey = (y - 728) / 30.0f;
                float mist = std::exp(-(ex * ex + ey * ey) * 1.3f) * smooth(0.30f, 0.72f, swirl) * 0.95f;
                here = mix(here, rgb(224, 214, 198), mist);
                V f;
                if (LOOP0 >= 0) {
                    float now = T, w = clamp01((now - LOOP0) / P);
                    V u1 = here, u2 = here;
                    V f1 = burn(u1, 412.89f + (x + 0.5f - FX - 412.89f) / FS, 282.45f + (y + 0.5f - FY - 282.45f) / FS);
                    T = now - P;
                    V f2 = burn(u2, 412.89f + (x + 0.5f - FX - 412.89f) / FS, 282.45f + (y + 0.5f - FY - 282.45f) / FS);
                    T = now;
                    here = mix(u1, u2, w);
                    f = mix(f1, f2, w);
                } else
                    f = burn(here, 412.89f + (x + 0.5f - FX - 412.89f) / FS, 282.45f + (y + 0.5f - FY - 282.45f) / FS);
                glow[(y + OY) * W + x] = f;
            }
        {
            std::vector<unsigned char> raw(W * CH * 3);
            FILE* f = std::fopen("ref.rgb", "rb");
            if (!f || std::fread(raw.data(), 1, raw.size(), f) != raw.size()) return 1;
            std::fclose(f);
            auto luma = [](V c) { return c.x * 0.3f + c.y * 0.6f + c.z * 0.1f; };
            const int centre[] = {390, 450, 515, 585, 655};
            constexpr int bands = 5, bins = 64;
            std::vector<float> mine[bands];
            std::vector<V> theirs[bands];
            const char* lut_in = std::getenv("LADDER_LUT_IN");
            const char* lut_out = std::getenv("LADDER_LUT_OUT");
            FILE* lut = lut_in ? std::fopen(lut_in, "rb") : nullptr;
            bool reused = lut != nullptr;
            if (lut) {
                for (int b = 0; b < bands; b++) {
                    unsigned n = 0;
                    if (std::fread(&n, sizeof n, 1, lut) != 1) return 1;
                    mine[b].resize(n);
                    theirs[b].resize(bins);
                    if (std::fread(mine[b].data(), sizeof(float), n, lut) != n) return 1;
                    if (std::fread(theirs[b].data(), sizeof(V), bins, lut) != (size_t)bins) return 1;
                }
                std::fclose(lut);
            } else {
                for (int b = 0; b < bands; b++) {
                    std::vector<std::pair<float, V>> ref;
                    for (int y = centre[b] - 35; y < centre[b] + 35; y++)
                        for (int x = 380; x < 660; x++) {
                            if (a[((y + OY) * W + x) * 4 + 3] < 250) continue;
                            const unsigned char* p = &raw[(y * W + x) * 3];
                            V c = rgb(p[0], p[1], p[2]);
                            ref.push_back({luma(c), c});
                            mine[b].push_back(luma(img[(y + OY) * W + x]));
                        }
                    std::sort(ref.begin(), ref.end(), [](auto& p, auto& q) { return p.first < q.first; });
                    std::sort(mine[b].begin(), mine[b].end());
                    for (int k = 0; k < bins; k++) {
                        size_t from = ref.size() * k / bins, to = ref.size() * (k + 1) / bins;
                        V sum = {0, 0, 0};
                        for (size_t n = from; n < to; n++) sum = sum + ref[n].second;
                        theirs[b].push_back(sum * (1.0f / (to - from)));
                    }
                }
                if (lut_out) {
                    FILE* o = std::fopen(lut_out, "wb");
                    for (int b = 0; b < bands; b++) {
                        unsigned n = mine[b].size();
                        std::fwrite(&n, sizeof n, 1, o);
                        std::fwrite(mine[b].data(), sizeof(float), n, o);
                        std::fwrite(theirs[b].data(), sizeof(V), bins, o);
                    }
                    std::fclose(o);
                }
            }
            for (int y = reused ? -OY : 360; y < 700; y++) {
                int b = 0;
                while (b < bands - 2 && y > centre[b + 1]) b++;
                float t = clamp01((y - centre[b]) / float(centre[b + 1] - centre[b]));
                for (int x = reused ? 0 : 380; x < (reused ? W : 660); x++) {
                    float cover = a[((y + OY) * W + x) * 4 + 3] / 255.0f;
                    if (cover <= 0) continue;
                    V& c = img[(y + OY) * W + x];
                    float l = luma(c);
                    auto look = [&](int k) {
                        float p = (std::lower_bound(mine[k].begin(), mine[k].end(), l) - mine[k].begin()) / float(mine[k].size()) * bins - 0.5f;
                        int n = std::max(0, std::min(bins - 2, (int)p));
                        return mix(theirs[k][n], theirs[k][n + 1], clamp01(p - n));
                    };
                    c = mix(c, mix(look(b), look(b + 1), t), cover * cover * 0.85f * (reused ? 1.0f : smooth(360, 385, y)) * (1 - smooth(670, 700, y)));
                }
            }
        }
        for (int pass = 0; pass < 6; pass++) {
            int radius = 9;
            for (int axis = 0; axis < 2; axis++) {
                std::vector<V> out(W * LH, {0, 0, 0});
                int fy = OY + (int)(282.45f + FY), fx = (int)(412.89f + FX);
                for (int y = std::max(radius, fy - (int)(142 * FS)); y < std::min(LH - radius, fy + (int)(258 * FS)); y++)
                    for (int x = std::max(radius, fx - (int)(133 * FS)); x < std::min(W - radius, fx + (int)(367 * FS)); x++) {
                        V sum = {0, 0, 0};
                        for (int k = -radius; k <= radius; k++) sum = sum + glow[axis ? (y + k) * W + x : y * W + x + k];
                        out[y * W + x] = sum * (1.0f / (2 * radius + 1));
                    }
                glow.swap(out);
            }
        }
        float wf = 6.2831853f / P;
        float flicker = 0.88f + 0.08f * std::sin(T * wf * 30) * std::sin(T * wf * 18 + 1.0f) + 0.06f * std::sin(T * wf * 52);
        for (int i = 0; i < W * LH; i++) {
            V g = glow[i] * (0.55f * flicker);
            V& c = img[i];
            c = {1 - (1 - c.x) * (1 - clamp01(g.x)), 1 - (1 - c.y) * (1 - clamp01(g.y)), 1 - (1 - c.z) * (1 - clamp01(g.z))};
        }
    }

    if (argc > 2) {
        std::vector<V> lit = img;
        float px = 578, py = 725, c = std::cos(ANGLE), s = std::sin(ANGLE);
        for (int y = 0; y < CH; y++)
            for (int x = 0; x < W; x++) {
                float ux = (x - px) / std::max(0.05f, std::cos(YAW));
                float uy = (y - py) / (1 + 0.12f * std::sin(YAW) * std::max(-1.0f, std::min(1.0f, ux / 120)));
                float sx = px + ux * c + uy * s, sy = py - ux * s + uy * c;
                if (sx < 0 || sx >= W - 1 || sy < 0 || sy >= CH - 1 || y > 760) continue;
                int ix = (int)sx, iy = (int)sy;
                float fx = sx - ix, fy = sy - iy;
                auto at = [&](std::vector<V>& buf) { auto q = [&](int a, int b) { return buf[(b + OY) * W + a]; }; return mix(mix(q(ix, iy), q(ix + 1, iy), fx), mix(q(ix, iy + 1), q(ix + 1, iy + 1), fx), fy); };
                float al = (held[iy * W + ix] * (1 - fx) + held[iy * W + ix + 1] * fx) * (1 - fy) + (held[(iy + 1) * W + ix] * (1 - fx) + held[(iy + 1) * W + ix + 1] * fx) * fy;
                float wisp = fbm({x / 26.0f, y / 11.0f, 5.3f}, 4) - 0.5f;
                al *= 1 - smooth(652, 672, y + wisp * 30);
                V full = at(lit), back = at(bare);
                V extra = V{std::max(0.0f, full.x - back.x), std::max(0.0f, full.y - back.y), std::max(0.0f, full.z - back.z)} * (1 - smooth(480, 540, sy));
                img[(y + OY) * W + x] = mix(bare[(y + OY) * W + x] + extra, full, al);
            }
    }
    FILE* out = std::fopen(argv[1], "wb");
    std::fprintf(out, "P6\n%d %d\n255\n", W, H);
    gen.seed(1000 + seed);
    std::normal_distribution<float> grain(0, 0.027f);
    for (int i = 0; i < W * H; i++) {
        float n = grain(gen);
        unsigned char px[3] = {(unsigned char)(clamp01(img[i].x + n + grain(gen) * 0.6f) * 255), (unsigned char)(clamp01(img[i].y + n) * 255), (unsigned char)(clamp01(img[i].z + n + grain(gen) * 0.6f) * 255)};
        std::fwrite(px, 1, 3, out);
    }
    std::fclose(out);
}
