import Dexie from 'dexie';

export const db = new Dexie('BiliMusicDB');

db.version(1).stores({
  folderCache: 'id', // mediaId as primary key
  playQueue: '++id, bvid', // auto-incrementing id, index on bvid
  folderPagination: 'id'
});

export default db;
